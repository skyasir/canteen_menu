"""Data behind the Menu Board page.

Deliberately built on the same resolver POS uses, so the board shows exactly
what the counter will show - not a second interpretation of the menu that
could drift from it.
"""

import frappe
from frappe.utils import flt, getdate

from canteen_menu.menu import get_active_cycle, get_menu_rows


@frappe.whitelist()
def get_menu_board(pos_profile: str, on_date: str | None = None) -> dict:
	"""What a canteen is selling on `on_date`, priced."""
	frappe.has_permission("Menu Cycle", throw=True)

	on_date = getdate(on_date)
	cycle = get_active_cycle(pos_profile, on_date)

	price_list = frappe.db.get_value("POS Profile", pos_profile, "selling_price_list")
	currency = frappe.db.get_value("Price List", price_list, "currency") if price_list else None

	dishes = [
		{
			"item_code": row.item_code,
			"item_name": row.item_name or row.item_code,
			"uom": row.uom,
			"rate": flt(row.rate),
			"planned_qty": flt(row.planned_qty),
		}
		for row in get_menu_rows(pos_profile, on_date)
	]

	details = (
		frappe.db.get_value("Menu Cycle", cycle.name, ["cycle_name", "branch"], as_dict=True)
		if cycle
		else None
	)

	return {
		"canteen": pos_profile,
		"date": str(on_date),
		"cycle": cycle.name if cycle else None,
		"cycle_name": details.cycle_name if details else None,
		"branch": details.branch if details else None,
		"from_date": str(cycle.from_date) if cycle else None,
		"to_date": str(cycle.to_date) if cycle and cycle.to_date else None,
		"dishes": dishes,
		"currency": currency,
		"price_list": price_list,
		"total_dishes": len(dishes),
		"total_planned": sum(d["planned_qty"] for d in dishes),
	}
