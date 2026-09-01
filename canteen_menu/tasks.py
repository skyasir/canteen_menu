"""Scheduled work for the Canteen Menu app."""

import frappe


def apply_scheduled_windows():
	"""Daily: move each menu onto the planned week that covers today.

	Saving is what makes it live - it rewrites Starts On / Until, marks the
	row Running Now, and pushes the menu's rates onto the price list for the
	new window.
	"""
	frappe.flags.mute_messages = True

	for name in frappe.get_all("Menu Cycle", filters={"is_active": 1}, pluck="name"):
		cycle = frappe.get_doc("Menu Cycle", name)
		if not cycle.schedule:
			continue

		try:
			if cycle.apply_scheduled_window():
				cycle.save(ignore_permissions=True)
				frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title=f"Menu Cycle {name}: could not apply the planned week",
				message=frappe.get_traceback(),
			)
