"""Menu rows moved from "Day No 1..N" to a named weekday.

Day 1 of a cycle is the weekday its `from_date` falls on, Day 2 the next day,
and so on. Templates have no start date, so their Day 1 is simply Monday.
"""

import frappe
from frappe.utils import add_days, getdate

from canteen_menu.menu import WEEKDAYS


def execute():
	if not frappe.db.has_column("Menu Cycle Item", "day_number"):
		return

	rows = frappe.db.sql(
		"""
		select item.name, item.day_number, item.parenttype, cycle.from_date
		from `tabMenu Cycle Item` item
		left join `tabMenu Cycle` cycle
			on cycle.name = item.parent and item.parenttype = 'Menu Cycle'
		where ifnull(item.weekday, '') = ''
		""",
		as_dict=True,
	)

	for row in rows:
		day = max(frappe.utils.cint(row.day_number) or 1, 1)

		if row.parenttype == "Menu Cycle" and row.from_date:
			weekday = WEEKDAYS[getdate(add_days(getdate(row.from_date), day - 1)).weekday()]
		else:
			weekday = WEEKDAYS[(day - 1) % 7]

		frappe.db.set_value("Menu Cycle Item", row.name, "weekday", weekday, update_modified=False)

	if rows:
		frappe.db.commit()
