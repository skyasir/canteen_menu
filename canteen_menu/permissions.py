"""Who sees the Canteen Menu app on the apps screen."""

import frappe


def check_app_permission() -> bool:
	if frappe.session.user == "Administrator":
		return True

	return bool(frappe.has_permission("Menu Cycle", ptype="read"))
