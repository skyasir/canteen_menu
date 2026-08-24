// Copyright (c) 2026, Yasir Shaikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Menu Cycle", {
	refresh(frm) {
		frm.trigger("set_menu_buttons");
	},

	menu_item_template(frm) {
		frm.trigger("set_menu_buttons");
	},

	set_menu_buttons(frm) {
		frm.clear_custom_buttons();

		if (frm.doc.menu_item_template) {
			frm.add_custom_button(__("Fetch Items from Template"), () => frm.trigger("fetch_template_items"));
		}

		if (!frm.is_new() && frm.doc.pos_profile) {
			frm.add_custom_button(__("Preview Today's Menu"), () => frm.trigger("preview_menu"));
		}
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

				// Skip rows already on the cycle for the same day, meal and item.
				const existing = new Set(
					(frm.doc.items || []).map((d) => `${d.day_number}|${d.meal_type}|${d.item_code}`)
				);

				let added = 0;
				rows.forEach((row) => {
					if (existing.has(`${row.day_number}|${row.meal_type}|${row.item_code}`)) return;
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

	preview_menu(frm) {
		frappe.call({
			method: "canteen_menu.api.pos.preview_menu",
			args: { pos_profile: frm.doc.pos_profile },
			callback: ({ message }) => {
				if (!message || !message.cycle) {
					frappe.msgprint({
						title: __("Nothing on the menu"),
						message: __("No active Menu Cycle covers today for {0}, so POS shows all items.", [
							frm.doc.pos_profile,
						]),
						indicator: "orange",
					});
					return;
				}

				const rows = (message.items || [])
					.map(
						(d) => `<tr>
							<td>${frappe.utils.escape_html(d.meal_type || "")}</td>
							<td>${frappe.utils.escape_html(d.item_code || "")}</td>
							<td>${frappe.utils.escape_html(d.item_name || "")}</td>
							<td class="text-right">${format_currency(d.rate)}</td>
						</tr>`
					)
					.join("");

				frappe.msgprint({
					title: __("Day {0} of {1}", [message.day_number, message.cycle]),
					message: rows
						? `<table class="table table-bordered">
								<thead><tr>
									<th>${__("Meal")}</th><th>${__("Item")}</th>
									<th>${__("Name")}</th><th class="text-right">${__("Rate")}</th>
								</tr></thead>
								<tbody>${rows}</tbody>
							</table>`
						: __("This cycle has nothing scheduled for today, so POS will show no items."),
					wide: true,
				});
			},
		});
	},
});
