"""Resolution of the live canteen menu.

A Menu Cycle lists the items a canteen sells between its start and end dates.
Everything that needs to know "what is on the menu right now" - the POS
override, the desk preview, the board, the tests - goes through here.
"""

import frappe
from frappe.query_builder import Order
from frappe.utils import getdate


def get_active_cycle(pos_profile: str, on_date=None) -> frappe._dict | None:
	"""The active Menu Cycle covering `on_date` for this POS Profile.

	Returns None when the canteen has no menu for that date - callers treat
	that as "do not restrict anything".
	"""
	if not pos_profile:
		return None

	on_date = getdate(on_date)
	cycle = frappe.qb.DocType("Menu Cycle")

	rows = (
		frappe.qb.from_(cycle)
		.select(cycle.name, cycle.from_date, cycle.to_date)
		.where(
			(cycle.pos_profile == pos_profile)
			& (cycle.is_active == 1)
			& (cycle.from_date <= on_date)
			# a blank end date means the menu has no end
			& (cycle.to_date.isnull() | (cycle.to_date >= on_date))
		)
		.orderby(cycle.from_date, order=Order.desc)
		.orderby(cycle.modified, order=Order.desc)
		.limit(1)
	).run(as_dict=True)

	return rows[0] if rows else None


def get_menu_rows(pos_profile: str, on_date=None) -> list[frappe._dict]:
	"""Every item the active menu puts on the counter on `on_date`."""
	cycle = get_active_cycle(pos_profile, on_date)
	if not cycle:
		return []

	return frappe.get_all(
		"Menu Cycle Item",
		filters={"parenttype": "Menu Cycle", "parent": cycle.name},
		fields=["item_code", "item_name", "uom", "planned_qty", "rate"],
		order_by="idx asc",
	)


def get_menu_item_codes(pos_profile: str, on_date=None) -> list[str] | None:
	"""Item codes sellable at this canteen on `on_date`.

	None means "no menu is configured, do not filter". An empty list means
	"a menu is running but lists nothing" - a real restriction.
	"""
	if not get_active_cycle(pos_profile, on_date):
		return None

	seen = {row.item_code for row in get_menu_rows(pos_profile, on_date) if row.item_code}
	return sorted(seen)
