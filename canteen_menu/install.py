"""First-run setup for the Canteen Menu app."""

import frappe

# Seeded once, then yours: rename, reorder, disable or add to them freely.
# Deliberately not shipped as fixtures, which would overwrite your edits on
# every migrate.
DEFAULT_MEALS = (
	("Breakfast", 10),
	("Brunch", 20),
	("Lunch", 30),
	("Tea", 40),
	("Snacks", 50),
	("Dinner", 60),
	("Supper", 70),
	("Other", 99),
)


def after_install():
	create_default_meal_types()


def create_default_meal_types():
	for meal, sequence in DEFAULT_MEALS:
		if frappe.db.exists("Meal Type", meal):
			continue

		frappe.get_doc({"doctype": "Meal Type", "meal_name": meal, "sequence": sequence}).insert(
			ignore_permissions=True
		)
