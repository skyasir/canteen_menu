# Copyright (c) 2026, Yasir Shaikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MenuItemTemplate(Document):
	def validate(self):
		for row in self.items:
			if not row.item_code:
				continue

			item_name, stock_uom = frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom"])
			if not row.item_name:
				row.item_name = item_name
			if not row.uom:
				row.uom = stock_uom
