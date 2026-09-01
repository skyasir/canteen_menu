"""Data behind the Menu Board page.

Deliberately built on the same resolver POS uses, so the board shows exactly
what the counter will show on each day - not a second interpretation of the
menu that could drift from it.
"""

import frappe
from frappe.utils import add_days, flt, getdate

from canteen_menu.menu import get_active_cycle, get_menu_rows, get_weekday


@frappe.whitelist()
def get_menu_board(pos_profile: str, on_date: str | None = None) -> dict:
	"""One week of menu for a canteen, grouped by meal and weekday."""
	frappe.has_permission("Menu Cycle", throw=True)

	on_date = getdate(on_date)
	monday = getdate(add_days(on_date, -on_date.weekday()))
	today = getdate()

	price_list = frappe.db.get_value("POS Profile", pos_profile, "selling_price_list")
	currency = frappe.db.get_value("Price List", price_list, "currency") if price_list else None

	days = []
	for offset in range(7):
		date = getdate(add_days(monday, offset))
		cycle = get_active_cycle(pos_profile, date)

		by_meal: dict[str, list[dict]] = {}
		for row in get_menu_rows(pos_profile, date):
			by_meal.setdefault(row.meal_type or frappe._("Unassigned"), []).append(
				{
					"item_code": row.item_code,
					"item_name": row.item_name or row.item_code,
					"rate": flt(row.rate),
					"planned_qty": flt(row.planned_qty),
				}
			)

		days.append(
			{
				"date": str(date),
				"weekday": get_weekday(date),
				"is_today": date == today,
				"is_past": date < today,
				"cycle": cycle.name if cycle else None,
				"cycle_name": frappe.db.get_value("Menu Cycle", cycle.name, "cycle_name") if cycle else None,
				"meals": by_meal,
			}
		)

	# Meals in serving order, and only the ones this week actually uses.
	ordered = frappe.get_all(
		"Meal Type", filters={"disabled": 0}, fields=["name"], order_by="sequence asc, name asc", pluck="name"
	)
	used = [meal for meal in ordered if any(meal in day["meals"] for day in days)]
	used += sorted({m for day in days for m in day["meals"]} - set(used))

	return {
		"canteen": pos_profile,
		"week_start": str(monday),
		"week_end": str(getdate(add_days(monday, 6))),
		"days": days,
		"meals": used,
		"currency": currency,
		"total_dishes": sum(len(items) for day in days for items in day["meals"].values()),
	}
