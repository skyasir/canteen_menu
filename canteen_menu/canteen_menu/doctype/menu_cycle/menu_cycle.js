// Copyright (c) 2026, Yasir Shaikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Menu Cycle", {
	refresh(frm) {
		frm.trigger("set_menu_buttons");
		frm.trigger("show_todays_menu");
	},

	menu_item_template(frm) {
		frm.trigger("set_menu_buttons");
	},

	pos_profile(frm) {
		frm.trigger("show_todays_menu");
	},

	set_menu_buttons(frm) {
		frm.clear_custom_buttons();

		if (frm.doc.menu_item_template) {
			frm.add_custom_button(__("Fetch Items from Template"), () => frm.trigger("fetch_template_items"));
		}
	},

	// Says in words what POS is serving right now, so nobody has to work it out.
	show_todays_menu(frm) {
		if (frm.is_new() || !frm.doc.pos_profile) {
			frm.set_intro("");
			return;
		}

		frappe.call({
			method: "canteen_menu.api.pos.preview_menu",
			args: { pos_profile: frm.doc.pos_profile },
			callback: ({ message }) => {
				if (!message) return;

				if (message.cycle !== frm.doc.name) {
					frm.set_intro(
						__("{0} is serving at {1} right now, not this menu.", [
							message.cycle_name || message.cycle || __("No menu"),
							frm.doc.pos_profile,
						]),
						"orange"
					);
					return;
				}

				const count = (message.items || []).length;
				frm.set_intro(
					count
						? __("Live at {0} — POS is showing the {1} item(s) below.", [frm.doc.pos_profile, count])
						: __("Live at {0}, but this menu lists no items, so POS shows nothing.", [
								frm.doc.pos_profile,
						  ]),
					count ? "blue" : "orange"
				);
			},
		});
	},

	fetch_template_items(frm) {
		frappe.call({
			method: "canteen_menu.api.template.get_template_items",
			args: { template: frm.doc.menu_item_template },
			freeze: true,
			freeze_message: __("Fetching template items..."),
			callback: ({ message: rows }) => {
				if (!rows || !rows.length) {
					frappe.msgprint(__("That template has no items yet."));
					return;
				}

				// Skip items already on the menu.
				const existing = new Set((frm.doc.items || []).map((d) => `${d.item_code}|${d.uom || ""}`));

				let added = 0;
				rows.forEach((row) => {
					if (existing.has(`${row.item_code}|${row.uom || ""}`)) return;
					frm.add_child("items", row);
					added += 1;
				});

				frm.refresh_field("items");
				frappe.show_alert({
					message: __("{0} of {1} row(s) added", [added, rows.length]),
					indicator: added ? "green" : "orange",
				});
			},
		});
	},
});
