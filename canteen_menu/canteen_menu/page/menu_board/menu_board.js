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
		this.page.set_secondary_action(__("Print"), () => window.print());

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
				this.dishes(data) +
				this.windows(data) +
				this.notes(data)
		);
	}

	title(data) {
		const c = data.cycle;
		const period = c
			? `${frappe.datetime.str_to_user(c.from_date)} — ${
					c.to_date ? frappe.datetime.str_to_user(c.to_date) : __("until further notice")
			  }`
			: "";
		return `
			<div class="mb-title">
				<div class="mb-canteen">${frappe.utils.escape_html(data.canteen)}</div>
				<div class="mb-sub">${
					c ? frappe.utils.escape_html(c.cycle_name || c.name) : __("No menu")
				}${period ? ` &middot; ${period}` : ""}</div>
				<div class="mb-printed">${__("As of")} ${frappe.datetime.str_to_user(data.date)}</div>
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
		const stat = (value, label) =>
			`<div class="mb-stat"><b>${value}</b><span>${label}</span></div>`;

		return `
			<div class="mb-stats">
				${stat(data.total_dishes, __("dishes"))}
				${data.total_planned ? stat(format_number(data.total_planned), __("planned")) : ""}
				${
					data.total_value
						? stat(format_currency(data.total_value, data.currency), __("menu value"))
						: ""
				}
			</div>`;
	}

	dishes(data) {
		if (!data.dishes.length) {
			return this.blank(__("This menu lists no items, so POS shows nothing at this counter."));
		}

		const cards = data.dishes
			.map(
				(dish) => `
				<div class="mb-dish">
					<div class="mb-dish-top">
						<div class="mb-dish-name">${frappe.utils.escape_html(dish.item_name)}</div>
						<div class="mb-dish-rate ${dish.rate ? "" : "mb-unpriced"}">${
							dish.rate ? format_currency(dish.rate, data.currency) : __("no price")
						}</div>
					</div>
					<div class="mb-dish-meta">
						<span class="mb-code">${frappe.utils.escape_html(dish.item_code)}</span>
						${dish.uom ? `<span>${frappe.utils.escape_html(dish.uom)}</span>` : ""}
						${
							dish.planned_qty
								? `<span class="mb-qty">${__("plan")} ${format_number(dish.planned_qty)}</span>`
								: ""
						}
					</div>
					${dish.notes ? `<div class="mb-dish-note">${frappe.utils.escape_html(dish.notes)}</div>` : ""}
				</div>`
			)
			.join("");

		return `<div class="mb-section-label">${__("Dishes")}</div><div class="mb-grid">${cards}</div>`;
	}

	windows(data) {
		if (!data.schedule || !data.schedule.length) return "";

		const rows = data.schedule
			.map(
				(w) => `
				<div class="mb-win ${w.is_current ? "is-current" : ""}">
					<span>${frappe.datetime.str_to_user(w.from_date)} — ${frappe.datetime.str_to_user(w.to_date)}</span>
					${w.notes ? `<span class="mb-win-note">${frappe.utils.escape_html(w.notes)}</span>` : ""}
					${w.is_current ? `<span class="mb-win-pill">${__("Running now")}</span>` : ""}
				</div>`
			)
			.join("");

		return `<div class="mb-section-label">${__("Planned Weeks")}</div><div class="mb-wins">${rows}</div>`;
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
			.menu-board { padding-bottom: 2rem; max-width: 100%; }

			.mb-title { margin-bottom: .75rem; }
			.mb-canteen { font-size: 1.5rem; font-weight: 650; color: var(--text-color, #1f272e); line-height: 1.2; }
			.mb-sub { color: var(--text-muted, #8d99a6); font-size: .88rem; margin-top: 4px; }
			.mb-printed { display: none; }

			.mb-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 1rem; }
			.mb-chip {
				display: inline-flex; align-items: baseline; gap: 5px;
				padding: 3px 10px; border-radius: 999px; font-size: .75rem;
				background: var(--bg-color, #f4f5f6); color: var(--text-color, #1f272e);
				border: 1px solid var(--border-color, #e2e6e9);
			}
			.mb-chip-k { color: var(--text-muted, #8d99a6); }
			.mb-chip-on { background: var(--bg-green, rgba(46,160,67,.14)); border-color: transparent; }
			.mb-chip-off { background: var(--bg-gray, rgba(140,150,160,.15)); border-color: transparent; }

			/* Left-aligned so nothing can be pushed off the right edge. */
			.mb-stats { display: flex; flex-wrap: wrap; gap: 2rem; margin-bottom: 1.5rem; }
			.mb-stat b {
				display: block; font-size: 1.5rem; font-weight: 650; line-height: 1.1;
				color: var(--text-color, #1f272e);
			}
			.mb-stat span {
				font-size: .7rem; text-transform: uppercase; letter-spacing: .06em;
				color: var(--text-muted, #8d99a6);
			}

			.mb-section-label {
				font-size: .72rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 600;
				color: var(--text-muted, #8d99a6); margin: 1.25rem 0 .6rem;
			}

			.mb-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }
			.mb-dish {
				background: var(--fg-color, #fff); border: 1px solid var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px); padding: 14px 16px;
				display: flex; flex-direction: column; gap: 8px;
			}
			.mb-dish-top { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
			.mb-dish-name { font-size: .98rem; font-weight: 600; line-height: 1.3; color: var(--text-color, #1f272e); }
			.mb-dish-rate { font-size: 1rem; font-weight: 650; white-space: nowrap; color: var(--blue-600, #2490ef); }
			.mb-unpriced { font-size: .72rem; font-weight: 500; color: var(--text-light, #b9c0c7); }
			.mb-dish-meta {
				display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
				font-size: .72rem; color: var(--text-muted, #8d99a6);
			}
			.mb-code { font-family: var(--font-stack-mono, monospace); }
			.mb-qty { background: var(--bg-color, #f4f5f6); padding: 2px 8px; border-radius: 999px; }
			.mb-dish-note {
				font-size: .75rem; color: var(--text-muted, #8d99a6);
				border-top: 1px dashed var(--border-color, #e2e6e9); padding-top: 7px;
			}

			.mb-wins { display: flex; flex-direction: column; gap: 6px; }
			.mb-win {
				display: flex; align-items: center; gap: 10px; padding: 8px 12px;
				border: 1px solid var(--border-color, #e2e6e9); border-radius: var(--border-radius-md, 8px);
				background: var(--fg-color, #fff); font-size: .85rem; color: var(--text-color, #1f272e);
			}
			.mb-win.is-current { border-color: var(--blue-500, #2490ef); }
			.mb-win-note { color: var(--text-muted, #8d99a6); font-size: .78rem; }
			.mb-win-pill {
				margin-left: auto; font-size: .65rem; font-weight: 650; text-transform: uppercase;
				letter-spacing: .04em; padding: 2px 9px; border-radius: 999px;
				background: var(--blue-500, #2490ef); color: #fff;
			}

			.mb-notes {
				background: var(--fg-color, #fff); border: 1px solid var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px); padding: 12px 16px;
				font-size: .85rem; color: var(--text-color, #1f272e);
			}

			.mb-blank {
				text-align: center; padding: 3rem 1rem; color: var(--text-muted, #8d99a6);
				background: var(--fg-color, #fff); border: 1px dashed var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px);
			}

			/* Print: hide the whole desk by visibility, then lift the board to the
			   page origin. Class-name independent, so a desk redesign cannot leak
			   the sidebar back onto the paper. Colours are forced light because the
			   board inherits the user's dark theme on screen. */
			@media print {
				@page { margin: 12mm; }
				body * { visibility: hidden !important; }
				.menu-board, .menu-board * { visibility: visible !important; }
				.menu-board {
					position: absolute !important; inset: 0 auto auto 0;
					width: 100% !important; padding: 0 !important; margin: 0 !important;
				}
				.menu-board, .menu-board * {
					color: #000 !important; background: #fff !important;
					box-shadow: none !important; text-shadow: none !important;
				}
				.mb-dish, .mb-win, .mb-notes, .mb-chip { border: 1px solid #999 !important; break-inside: avoid; }
				.mb-sub, .mb-chip-k, .mb-dish-meta, .mb-stat span, .mb-section-label, .mb-dish-note {
					color: #444 !important;
				}
				.mb-win-pill { border: 1px solid #000 !important; }
				.mb-printed { display: block; font-size: .75rem; color: #444 !important; margin-top: 4px; }
				.mb-grid { grid-template-columns: repeat(3, 1fr) !important; }
			}
		</style>`).appendTo(document.head);
	}
}
