// Copyright (c) 2026, Yasir Shaikh and contributors
// For license information, please see license.txt

frappe.pages["menu-board"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Menu Board"),
		single_column: true,
	});
	wrapper.menu_board = new MenuBoard(page);
};

frappe.pages["menu-board"].on_page_show = function (wrapper) {
	wrapper.menu_board && wrapper.menu_board.refresh();
};

class MenuBoard {
	constructor(page) {
		this.page = page;
		this.inject_styles();
		this.make_controls();
		this.body = $('<div class="menu-board">').appendTo(this.page.main);
		this.refresh();
	}

	make_controls() {
		this.canteen_field = this.page.add_field({
			fieldtype: "Link",
			options: "POS Profile",
			label: __("Canteen"),
			fieldname: "pos_profile",
			change: () => this.refresh(),
		});

		this.date_field = this.page.add_field({
			fieldtype: "Date",
			label: __("On"),
			fieldname: "on_date",
			default: frappe.datetime.get_today(),
			change: () => this.refresh(),
		});
		this.date_field.set_value(frappe.datetime.get_today());

		this.page.add_inner_button(__("Today"), () =>
			this.date_field.set_value(frappe.datetime.get_today())
		);

		frappe.db.get_list("POS Profile", { limit: 1, pluck: "name" }).then((names) => {
			if (names && names.length && !this.canteen_field.get_value()) {
				this.canteen_field.set_value(names[0]);
			}
		});
	}

	refresh() {
		const canteen = this.canteen_field && this.canteen_field.get_value();
		if (!canteen) {
			this.body.html(this.blank(__("Pick a canteen to see what it is serving.")));
			return;
		}

		frappe.call({
			method: "canteen_menu.api.board.get_menu_board",
			args: { pos_profile: canteen, on_date: this.date_field.get_value() },
			callback: ({ message }) => message && this.render(message),
		});
	}

	render(data) {
		this.page.set_indicator(
			data.total_dishes ? __("{0} on the menu", [data.total_dishes]) : __("No menu"),
			data.total_dishes ? "green" : "orange"
		);

		if (!data.cycle) {
			this.body.html(
				this.title(data) +
					this.blank(
						__("No menu runs at {0} on this date, so POS shows the full item list.", [data.canteen])
					)
			);
			return;
		}

		this.body.html(
			this.title(data) +
				this.facts(data) +
				this.stats(data) +
				this.dish_table(data) +
				this.windows(data) +
				this.notes(data)
		);
	}

	title(data) {
		const c = data.cycle;
		const period = `${frappe.datetime.str_to_user(c.from_date)} — ${
			c.to_date ? frappe.datetime.str_to_user(c.to_date) : __("until further notice")
		}`;
		return `
			<div class="mb-title">
				<div class="mb-canteen">${frappe.utils.escape_html(data.canteen)}</div>
				<div class="mb-sub">${frappe.utils.escape_html(c.cycle_name || c.name)} &middot; ${period}</div>
			</div>`;
	}

	facts(data) {
		const c = data.cycle;
		const chip = (label, value) =>
			value
				? `<span class="mb-chip"><span class="mb-chip-k">${label}</span>${frappe.utils.escape_html(
						String(value)
				  )}</span>`
				: "";

		return `
			<div class="mb-chips">
				${chip(__("Branch"), c.branch)}
				${chip(__("Company"), c.company)}
				${chip(__("POS Profile"), c.pos_profile)}
				${chip(__("Price List"), data.price_list)}
				${chip(__("Template"), c.template)}
				<span class="mb-chip ${c.is_active ? "mb-chip-on" : "mb-chip-off"}">${
					c.is_active ? __("Active") : __("Inactive")
				}</span>
			</div>`;
	}

	stats(data) {
		const stat = (value, label) => `<div class="mb-stat"><b>${value}</b><span>${label}</span></div>`;
		return `
			<div class="mb-stats">
				${stat(data.total_dishes, __("dishes"))}
				${data.total_planned ? stat(format_number(data.total_planned), __("planned")) : ""}
				${data.total_value ? stat(format_currency(data.total_value, data.currency), __("menu value")) : ""}
			</div>`;
	}

	dish_table(data) {
		if (!data.dishes.length) {
			return this.blank(__("This menu lists no items, so POS shows nothing at this counter."));
		}

		const rows = data.dishes
			.map((dish, i) => {
				const amount = dish.rate * (dish.planned_qty || 0);
				return `
				<tr>
					<td class="mb-num">${i + 1}</td>
					<td>
						<div class="mb-dish-name">${frappe.utils.escape_html(dish.item_name)}</div>
						${dish.notes ? `<div class="mb-dish-note">${frappe.utils.escape_html(dish.notes)}</div>` : ""}
					</td>
					<td class="mb-code">${frappe.utils.escape_html(dish.item_code)}</td>
					<td>${frappe.utils.escape_html(dish.uom || "")}</td>
					<td class="mb-right">${dish.planned_qty ? format_number(dish.planned_qty) : "—"}</td>
					<td class="mb-right">${
						dish.rate
							? format_currency(dish.rate, data.currency)
							: `<span class="mb-unpriced">${__("no price")}</span>`
					}</td>
					<td class="mb-right">${amount ? format_currency(amount, data.currency) : "—"}</td>
				</tr>`;
			})
			.join("");

		return `
			<div class="mb-section-label">${__("Dishes")}</div>
			<div class="mb-scroll">
				<table class="mb-table">
					<thead>
						<tr>
							<th class="mb-num">#</th>
							<th>${__("Dish")}</th>
							<th>${__("Item Code")}</th>
							<th>${__("UOM")}</th>
							<th class="mb-right">${__("Planned")}</th>
							<th class="mb-right">${__("Rate")}</th>
							<th class="mb-right">${__("Amount")}</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
					<tfoot>
						<tr>
							<td colspan="4">${__("Total")}</td>
							<td class="mb-right">${data.total_planned ? format_number(data.total_planned) : "—"}</td>
							<td></td>
							<td class="mb-right">${
								data.total_value ? format_currency(data.total_value, data.currency) : "—"
							}</td>
						</tr>
					</tfoot>
				</table>
			</div>`;
	}

	windows(data) {
		if (!data.schedule || !data.schedule.length) return "";

		const rows = data.schedule
			.map(
				(w) => `
				<tr class="${w.is_current ? "is-current" : ""}">
					<td>${frappe.datetime.str_to_user(w.from_date)}</td>
					<td>${frappe.datetime.str_to_user(w.to_date)}</td>
					<td>${w.notes ? frappe.utils.escape_html(w.notes) : ""}</td>
					<td class="mb-right">${
						w.is_current ? `<span class="mb-pill">${__("Running now")}</span>` : ""
					}</td>
				</tr>`
			)
			.join("");

		return `
			<div class="mb-section-label">${__("Planned Weeks")}</div>
			<div class="mb-scroll">
				<table class="mb-table">
					<thead>
						<tr>
							<th>${__("Starts On")}</th><th>${__("Until")}</th>
							<th>${__("Notes")}</th><th></th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			</div>`;
	}

	notes(data) {
		if (!data.cycle.notes) return "";
		return `<div class="mb-section-label">${__("Notes")}</div><div class="mb-notes">${
			data.cycle.notes
		}</div>`;
	}

	blank(message) {
		return `<div class="mb-blank">${message}</div>`;
	}

	inject_styles() {
		if (document.getElementById("menu-board-styles")) return;

		$(`<style id="menu-board-styles">
			/* Everything here is width-safe: the board never draws past its
			   container, and long names or notes wrap instead of pushing the
			   layout sideways. min-width:0 is what stops grid and flex children
			   from refusing to shrink. */
			.menu-board {
				padding: 0 8px 2rem; max-width: 100%; box-sizing: border-box;
				overflow-wrap: anywhere;
			}
			.menu-board * { box-sizing: border-box; min-width: 0; }

			.mb-title { margin-bottom: .75rem; }
			.mb-canteen { font-size: 1.5rem; font-weight: 650; line-height: 1.2; color: var(--text-color, #1f272e); }
			.mb-sub { color: var(--text-muted, #8d99a6); font-size: .88rem; margin-top: 4px; }

			.mb-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 1rem; }
			.mb-chip {
				display: inline-flex; align-items: baseline; gap: 5px; max-width: 100%;
				padding: 3px 10px; border-radius: 999px; font-size: .75rem;
				background: var(--bg-color, #f4f5f6); color: var(--text-color, #1f272e);
				border: 1px solid var(--border-color, #e2e6e9);
			}
			.mb-chip-k { color: var(--text-muted, #8d99a6); flex-shrink: 0; }
			.mb-chip-on { background: var(--bg-green, rgba(46,160,67,.14)); border-color: transparent; }
			.mb-chip-off { background: var(--bg-gray, rgba(140,150,160,.15)); border-color: transparent; }

			.mb-stats { display: flex; flex-wrap: wrap; gap: 2rem; margin-bottom: 1.25rem; }
			.mb-stat b { display: block; font-size: 1.5rem; font-weight: 650; line-height: 1.1; color: var(--text-color, #1f272e); }
			.mb-stat span {
				font-size: .7rem; text-transform: uppercase; letter-spacing: .06em;
				color: var(--text-muted, #8d99a6);
			}

			.mb-section-label {
				font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 600;
				color: var(--text-muted, #8d99a6); margin: 1.5rem 0 .6rem;
			}

			/* A table that is wider than the page scrolls inside its own box
			   rather than spilling out of it. */
			.mb-scroll {
				overflow-x: auto; max-width: 100%;
				border: 1px solid var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px);
				background: var(--fg-color, #fff);
			}
			.mb-table { width: 100%; border-collapse: collapse; font-size: .87rem; }
			.mb-table th, .mb-table td {
				padding: 10px 14px; text-align: left; vertical-align: top;
				border-bottom: 1px solid var(--border-color, #e2e6e9);
			}
			.mb-table thead th {
				font-size: .7rem; text-transform: uppercase; letter-spacing: .06em; font-weight: 600;
				color: var(--text-muted, #8d99a6); white-space: nowrap;
				background: var(--bg-color, #f4f5f6);
			}
			.mb-table tbody tr:last-child td { border-bottom: 0; }
			.mb-table tbody tr:hover td { background: var(--bg-color, #f4f5f6); }
			.mb-table tfoot td {
				font-weight: 650; color: var(--text-color, #1f272e);
				border-top: 2px solid var(--border-color, #e2e6e9); border-bottom: 0;
				background: var(--bg-color, #f4f5f6);
			}
			.mb-right { text-align: right; white-space: nowrap; }
			.mb-num { width: 40px; color: var(--text-muted, #8d99a6); }
			.mb-code { font-family: var(--font-stack-mono, monospace); font-size: .8rem; color: var(--text-muted, #8d99a6); }
			.mb-dish-name { font-weight: 600; color: var(--text-color, #1f272e); }
			.mb-dish-note { font-size: .78rem; color: var(--text-muted, #8d99a6); margin-top: 3px; }
			.mb-unpriced { color: var(--text-light, #b9c0c7); font-size: .8rem; }
			.mb-table tr.is-current td { background: var(--bg-blue, rgba(36,144,239,.08)); }
			.mb-pill {
				display: inline-block; font-size: .65rem; font-weight: 650; text-transform: uppercase;
				letter-spacing: .04em; padding: 2px 9px; border-radius: 999px; white-space: nowrap;
				background: var(--blue-500, #2490ef); color: #fff;
			}

			.mb-notes {
				background: var(--fg-color, #fff); border: 1px solid var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px); padding: 12px 16px;
				font-size: .85rem; color: var(--text-color, #1f272e); max-width: 100%;
			}
			.mb-notes p:last-child { margin-bottom: 0; }

			.mb-blank {
				text-align: center; padding: 3rem 1rem; color: var(--text-muted, #8d99a6);
				background: var(--fg-color, #fff); border: 1px dashed var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px);
			}
		</style>`).appendTo(document.head);
	}
}
