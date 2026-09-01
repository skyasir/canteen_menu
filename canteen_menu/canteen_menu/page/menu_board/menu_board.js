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
		this.date = frappe.datetime.get_today();
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

		this.page.add_inner_button(__("◀"), () => this.shift_week(-7));
		this.page.add_inner_button(__("Today"), () => {
			this.date = frappe.datetime.get_today();
			this.refresh();
		});
		this.page.add_inner_button(__("▶"), () => this.shift_week(7));

		this.page.set_secondary_action(__("Print"), () => window.print());

		// Default to the first canteen so the board is never blank on arrival.
		frappe.db.get_list("POS Profile", { limit: 1, pluck: "name" }).then((names) => {
			if (names && names.length && !this.canteen_field.get_value()) {
				this.canteen_field.set_value(names[0]);
			}
		});
	}

	shift_week(days) {
		this.date = frappe.datetime.add_days(this.date, days);
		this.refresh();
	}

	refresh() {
		const canteen = this.canteen_field && this.canteen_field.get_value();
		if (!canteen) {
			this.body.html(this.empty_state(__("Pick a canteen to see its week.")));
			return;
		}

		frappe.call({
			method: "canteen_menu.api.board.get_menu_board",
			args: { pos_profile: canteen, on_date: this.date },
			callback: ({ message }) => message && this.render(message),
		});
	}

	render(data) {
		this.page.set_title(__("Menu Board"));
		this.page.set_indicator(
			data.total_dishes ? __("{0} dishes this week", [data.total_dishes]) : __("Nothing planned"),
			data.total_dishes ? "green" : "orange"
		);

		if (!data.meals.length) {
			this.body.html(
				this.summary(data) +
					this.empty_state(
						__("No menu runs at {0} in this week. POS shows the full item list on these days.", [
							data.canteen,
						])
					)
			);
			return;
		}

		const head = data.days
			.map(
				(day) => `
				<div class="mb-day-head ${day.is_today ? "is-today" : ""} ${day.is_past ? "is-past" : ""}">
					<div class="mb-day-name">${__(day.weekday).slice(0, 3)}</div>
					<div class="mb-day-date">${frappe.datetime.str_to_user(day.date)}</div>
					${day.is_today ? `<div class="mb-today-pill">${__("Today")}</div>` : ""}
				</div>`
			)
			.join("");

		const rows = data.meals
			.map((meal) => {
				const cells = data.days
					.map((day) => {
						const items = day.meals[meal] || [];
						if (!items.length) {
							return `<div class="mb-cell ${day.is_today ? "is-today" : ""}"><span class="mb-empty">—</span></div>`;
						}
						const chips = items
							.map(
								(item) => `
								<div class="mb-dish" title="${frappe.utils.escape_html(item.item_code)}">
									<span class="mb-dish-name">${frappe.utils.escape_html(item.item_name)}</span>
									${item.rate ? `<span class="mb-dish-rate">${format_currency(item.rate, data.currency)}</span>` : ""}
								</div>`
							)
							.join("");
						return `<div class="mb-cell ${day.is_today ? "is-today" : ""}">${chips}</div>`;
					})
					.join("");
				return `<div class="mb-meal-label">${__(meal)}</div>${cells}`;
			})
			.join("");

		this.body.html(`
			${this.summary(data)}
			<div class="mb-grid-wrap">
				<div class="mb-grid">
					<div class="mb-corner"></div>
					${head}
					${rows}
				</div>
			</div>
		`);
	}

	summary(data) {
		const cycles = [...new Set(data.days.map((d) => d.cycle_name).filter(Boolean))];
		return `
			<div class="mb-summary">
				<div>
					<div class="mb-canteen">${frappe.utils.escape_html(data.canteen)}</div>
					<div class="mb-week">${frappe.datetime.str_to_user(data.week_start)} — ${frappe.datetime.str_to_user(
						data.week_end
					)}</div>
				</div>
				<div class="mb-cycles">${
					cycles.length
						? cycles.map((c) => `<span class="mb-tag">${frappe.utils.escape_html(c)}</span>`).join("")
						: `<span class="mb-tag mb-tag-muted">${__("No menu")}</span>`
				}</div>
			</div>`;
	}

	empty_state(message) {
		return `<div class="mb-blank">${message}</div>`;
	}

	inject_styles() {
		if (document.getElementById("menu-board-styles")) return;

		$(`<style id="menu-board-styles">
			.menu-board { padding-bottom: 2rem; }

			.mb-summary {
				display: flex; align-items: center; justify-content: space-between; gap: 1rem;
				flex-wrap: wrap; margin: 0 0 1rem 0;
			}
			.mb-canteen { font-size: 1.35rem; font-weight: 650; color: var(--text-color, #1f272e); }
			.mb-week { color: var(--text-muted, #8d99a6); font-size: 0.85rem; margin-top: 2px; }
			.mb-tag {
				display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 0.75rem;
				background: var(--bg-blue, rgba(36,144,239,.12)); color: var(--blue-600, #2490ef);
				margin-left: 6px; font-weight: 550;
			}
			.mb-tag-muted { background: var(--bg-gray, rgba(140,150,160,.15)); color: var(--text-muted, #8d99a6); }

			.mb-grid-wrap { overflow-x: auto; }
			.mb-grid {
				display: grid;
				grid-template-columns: 110px repeat(7, minmax(150px, 1fr));
				gap: 8px; min-width: 900px;
			}

			.mb-corner { }
			.mb-day-head {
				text-align: center; padding: 10px 6px; border-radius: var(--border-radius-md, 8px);
				background: var(--fg-color, #fff); border: 1px solid var(--border-color, #e2e6e9);
			}
			.mb-day-head.is-today {
				border-color: var(--blue-500, #2490ef);
				box-shadow: 0 0 0 1px var(--blue-500, #2490ef) inset;
			}
			.mb-day-head.is-past { opacity: .55; }
			.mb-day-name { font-weight: 650; color: var(--text-color, #1f272e); letter-spacing: .02em; }
			.mb-day-date { font-size: .75rem; color: var(--text-muted, #8d99a6); margin-top: 1px; }
			.mb-today-pill {
				display: inline-block; margin-top: 5px; padding: 1px 8px; border-radius: 999px;
				font-size: .65rem; font-weight: 650; text-transform: uppercase; letter-spacing: .04em;
				background: var(--blue-500, #2490ef); color: #fff;
			}

			.mb-meal-label {
				display: flex; align-items: center; font-weight: 600; font-size: .8rem;
				text-transform: uppercase; letter-spacing: .05em;
				color: var(--text-muted, #8d99a6); padding-right: 4px;
			}

			.mb-cell {
				background: var(--fg-color, #fff); border: 1px solid var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px); padding: 8px; min-height: 62px;
				display: flex; flex-direction: column; gap: 6px;
			}
			.mb-cell.is-today { border-color: var(--blue-500, #2490ef); }
			.mb-empty { color: var(--text-light, #c0c6cc); margin: auto; font-size: 1rem; }

			.mb-dish {
				display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
				padding: 6px 8px; border-radius: 6px;
				background: var(--bg-color, #f4f5f6);
			}
			.mb-dish-name { font-size: .82rem; color: var(--text-color, #1f272e); line-height: 1.25; }
			.mb-dish-rate { font-size: .78rem; font-weight: 600; color: var(--text-muted, #8d99a6); white-space: nowrap; }

			.mb-blank {
				text-align: center; padding: 3rem 1rem; color: var(--text-muted, #8d99a6);
				background: var(--fg-color, #fff); border: 1px dashed var(--border-color, #e2e6e9);
				border-radius: var(--border-radius-md, 8px);
			}

			@media print {
				.page-head, .navbar, .layout-side-section, .page-actions, .sidebar { display: none !important; }
				.mb-grid { min-width: 0; }
				.mb-cell, .mb-day-head { border-color: #bbb !important; }
				.mb-dish { background: #f3f3f3 !important; }
			}
		</style>`).appendTo(document.head);
	}
}
