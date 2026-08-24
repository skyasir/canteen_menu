"""Pulling a Menu Item Template's rows into a Menu Cycle."""

import frappe

TEMPLATE_ROW_FIELDS = (
	"weekday",
	"meal_type",
	"item_code",
	"item_name",
	"uom",
	"planned_qty",
	"rate",
	"notes",
)


@frappe.whitelist()
def get_template_items(template: str) -> list[dict]:
	"""Rows of a template, shaped for appending to a Menu Cycle's items grid."""
	frappe.has_permission("Menu Item Template", throw=True)

	doc = frappe.get_cached_doc("Menu Item Template", template)

	return [{field: row.get(field) for field in TEMPLATE_ROW_FIELDS} for row in doc.items]
