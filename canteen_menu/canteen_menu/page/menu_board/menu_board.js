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

		this.page.add_inner_button(__("Today"), () => {
			this.date_field.set_value(frappe.datetime.get_today());
		});
		this.page.set_secondary_action(__("Print"), () => window.print());

		// Default to the first canteen so the board is never blank on arrival.
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
				this.header(data) +
					this.blank(
						__("No menu runs at {0} on this date, so POS shows the full item list.", [data.canteen])
					)
			);
			return;
		}

		const cards = data.dishes
			.map(
				(dish) => `
				<div class="mb-dish">
					<div class="mb-dish-top">
						<div class="mb-dish-name">${frappe.utils.escape_html(dish.item_name)}</div>
						${dish.rate ? `<div class="mb-dish-rate">${format_currency(dish.rate, data.currency)}</div>` : ""}
					</div>
					<div class="mb-dish-foot">
						<span class="mb-code">${frappe.utils.escape_html(dish.item_code)}</span>
						${
							dish.planned_qty
								? `<span class="mb-qty">${__("plan")} ${format_number(dish.planned_qty)} ${frappe.utils.escape_html(
										dish.uom || ""
								  )}</span>`
								: ""
						}
					</div>
				</div>`
			)
			.join("");

		this.body.html(
			this.header(data) +
				(data.dishes.length
					? `<div class="mb-grid">${cards}</div>`
					: this.blank(__("This menu lists no items, so POS shows nothing at this counter.")))
		);
	}

	header(data) {
		const period = data.from_date
			? `${frappe.datetime.str_to_user(data.from_date)} — ${
					data.to_date ? frappe.datetime.str_to_user(data.to_date) : __("until further notice")
			  }`
			: "";

		return `
			<div class="mb-head">
				<div>
					<div class="mb-canteen">${frappe.utils.escape_html(data.canteen)}</div>
					<div class="mb-sub">${
						data.cycle_name ? frappe.utils.escape_html(data.cycle_name) : __("No menu")
					}${period ? ` &middot; ${period}` : ""}</div>
				</div>
				<div class="mb-stats">
					<div class="mb-stat"><b>${data.total_dishes}</b><span>${__("dishes")}</span></div>
					${
						data.total_planned
							? `<div class="mb-stat"><b>${format_number(data.total_planned)}</b><span>${__(
									"planned"
							  )}</span></div>`
							: ""
					}
				</div>
			</div>`;
	}

	blank(message) {
		return `<div class="mb-blank">${message}</div>`;
	}

	inject_styles() {
		if (document.getElementById("menu-board-styles")) return;

		$(`<style id="menu-board-styles">
			.menu-board { padding-bottom: 2rem; }

			.mb-head {
				display: flex; align-items: center; justify-content: space-between;
				gap: 1rem; flex-wrap: wrap; margin-bottom: 1.25rem;
			}
			.mb-canteen { font-size: 1.4rem; font-weight: 650; color: var(--text-color, #1f272e); }
			.mb-sub { color: var(--text-muted, #8d99a6); font-size: .85rem; margin-top: 3px; }
			.mb-stats { display: flex; gap: 1.5rem; }
			.mb-stat { text-align: right; }
			.mb-stat b { display: block; font-size: 1.4rem; font-weight: 650; color: var(--text-color, #1f272e); }
			.mb-stat span {
				font-size: .7rem; text-transform: uppercase; letter-spacing: .06em;
				color: var(--text-muted, #8d99a6);
			}

			.mb-grid {
				display: grid; gap: 12px;
				grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
			}

			.mb-dish {
				background: var(--fg-color, #fff);
				border: 1px solid var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px);
				padding: 14px 16px; display: flex; flex-direction: column; gap: 10px;
				transition: border-color .12s ease;
			}
			.mb-dish:hover { border-color: var(--blue-500, #2490ef); }
			.mb-dish-top { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
			.mb-dish-name {
				font-size: .98rem; font-weight: 600; line-height: 1.3;
				color: var(--text-color, #1f272e);
			}
			.mb-dish-rate {
				font-size: 1rem; font-weight: 650; white-space: nowrap;
				color: var(--blue-600, #2490ef);
			}
			.mb-dish-foot {
				display: flex; align-items: center; justify-content: space-between; gap: 8px;
				font-size: .72rem; color: var(--text-muted, #8d99a6);
			}
			.mb-code { font-family: var(--font-stack-mono, monospace); }
			.mb-qty {
				background: var(--bg-color, #f4f5f6); padding: 2px 8px; border-radius: 999px;
				white-space: nowrap;
			}

			.mb-blank {
				text-align: center; padding: 3rem 1rem; color: var(--text-muted, #8d99a6);
				background: var(--fg-color, #fff);
				border: 1px dashed var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px);
			}

			@media print {
				.page-head, .navbar, .layout-side-section, .page-actions, .sidebar { display: none !important; }
				.mb-dish { border-color: #bbb !important; break-inside: avoid; }
				.mb-dish-rate { color: #000 !important; }
			}
		</style>`).appendTo(document.head);
	}
}
