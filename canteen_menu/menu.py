"""Resolution of the live canteen menu.

Answers two questions for a canteen (a POS Profile) on a given date:
which Menu Cycle is running, and which items that cycle puts on the counter
today. Everything that needs to know "what is on the menu right now" - the
POS override, the desk preview, the tests - goes through here.
"""

import frappe
from frappe.utils import cint, getdate


def get_active_cycle(pos_profile: str, on_date=None) -> frappe._dict | None:
	"""The active Menu Cycle covering `on_date` for this POS Profile.

	Returns None when the canteen has no menu for that date - callers treat
	that as "do not restrict anything".
	"""
	if not pos_profile:
		return None

	on_date = getdate(on_date)
	cycles = frappe.get_all(
		"Menu Cycle",
		filters={
			"pos_profile": pos_profile,
			"is_active": 1,
			"from_date": ["<=", on_date],
			"to_date": [">=", on_date],
		},
		fields=["name", "from_date", "to_date", "rotation_type", "cycle_length"],
		order_by="from_date desc, modified desc",
		limit=1,
	)

	return cycles[0] if cycles else None


def get_day_number(cycle, on_date=None) -> int:
	"""Which day of the rotation `on_date` falls on. `from_date` is day 1."""
	on_date = getdate(on_date)
	from_date = getdate(cycle.from_date)
	length = cint(cycle.cycle_length) or 1

	if on_date < from_date:
		return 1

	if cycle.rotation_type == "Weekly":
		elapsed = (on_date - from_date).days // 7
	elif cycle.rotation_type == "Monthly":
		elapsed = (on_date.year - from_date.year) * 12 + (on_date.month - from_date.month)
	else:
		elapsed = (on_date - from_date).days

	return (elapsed % length) + 1


def get_menu_rows(pos_profile: str, on_date=None) -> list[frappe._dict]:
	"""Menu Cycle Item rows served at this canteen on `on_date`."""
	cycle = get_active_cycle(pos_profile, on_date)
	if not cycle:
		return []

	day = get_day_number(cycle, on_date)

	return frappe.get_all(
		"Menu Cycle Item",
		filters={
			"parenttype": "Menu Cycle",
			"parent": cycle.name,
			"day_number": day,
		},
		fields=["item_code", "item_name", "meal_type", "uom", "planned_qty", "rate", "day_number"],
		order_by="idx asc",
	)


def get_menu_item_codes(pos_profile: str, on_date=None) -> list[str] | None:
	"""Item codes sellable at this canteen on `on_date`.

	None means "no menu is configured, do not filter". An empty list means
	"a menu is running but nothing is scheduled today" - a real restriction.
	"""
	if not get_active_cycle(pos_profile, on_date):
		return None

	seen = {row.item_code for row in get_menu_rows(pos_profile, on_date) if row.item_code}
	return sorted(seen)
