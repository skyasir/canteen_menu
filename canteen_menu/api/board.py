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
	"""Everything the menu running at this canteen on `on_date` holds."""
	frappe.has_permission("Menu Cycle", throw=True)

	on_date = getdate(on_date)
	active = get_active_cycle(pos_profile, on_date)

	price_list = frappe.db.get_value("POS Profile", pos_profile, "selling_price_list")
	currency = frappe.db.get_value("Price List", price_list, "currency") if price_list else None

	board = {
		"canteen": pos_profile,
		"date": str(on_date),
		"price_list": price_list,
		"currency": currency,
		"cycle": None,
		"dishes": [],
		"schedule": [],
		"total_dishes": 0,
		"total_planned": 0.0,
		"total_value": 0.0,
	}

	if not active:
		return board

	cycle = frappe.get_doc("Menu Cycle", active.name)

	board["cycle"] = {
		"name": cycle.name,
		"cycle_name": cycle.cycle_name,
		"branch": cycle.branch,
		"company": cycle.company,
		"pos_profile": cycle.pos_profile,
		"template": cycle.menu_item_template,
		"is_active": cycle.is_active,
		"from_date": str(cycle.from_date) if cycle.from_date else None,
		"to_date": str(cycle.to_date) if cycle.to_date else None,
		"notes": cycle.notes,
	}

	board["dishes"] = [
		{
			"item_code": row.item_code,
			"item_name": row.item_name or row.item_code,
			"uom": row.uom,
			"rate": flt(row.rate),
			"planned_qty": flt(row.planned_qty),
			"notes": row.notes,
		}
		for row in get_menu_rows(pos_profile, on_date)
	]

	board["schedule"] = [
		{
			"from_date": str(row.from_date) if row.from_date else None,
			"to_date": str(row.to_date) if row.to_date else None,
			"is_current": row.is_current,
			"notes": row.notes,
		}
		for row in cycle.schedule
	]

	board["total_dishes"] = len(board["dishes"])
	board["total_planned"] = sum(d["planned_qty"] for d in board["dishes"])
	board["total_value"] = sum(d["rate"] * (d["planned_qty"] or 1) for d in board["dishes"])

	return board
