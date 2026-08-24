# Copyright (c) 2026, Yasir Shaikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate


class MenuCycle(Document):
	def validate(self):
		self.validate_dates()
		self.validate_cycle_length()
		self.validate_items_present()
		self.validate_day_numbers()
		self.validate_unique_rows()
		self.validate_no_overlapping_cycle()
		self.validate_consistent_rates()
		self.fill_item_details()

	def on_update(self):
		self.sync_menu_rates()

	def validate_dates(self):
		if self.from_date and self.to_date and getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date cannot be before From Date"))

	def validate_cycle_length(self):
		if cint(self.cycle_length) < 1:
			frappe.throw(_("Cycle Length (Days) must be at least 1"))

	def validate_items_present(self):
		if not self.items:
			frappe.throw(_("Add at least one menu item"))

	def validate_day_numbers(self):
		for row in self.items:
			day = cint(row.day_number)
			if day < 1 or day > cint(self.cycle_length):
				frappe.throw(
					_("Row #{0}: Day No {1} must be between 1 and {2}").format(
						row.idx, day, self.cycle_length
					)
				)

	def validate_unique_rows(self):
		seen: dict[tuple, int] = {}
		for row in self.items:
			key = (cint(row.day_number), row.meal_type, row.item_code)
			if key in seen:
				frappe.throw(
					_("Row #{0}: {1} is already listed for Day {2} {3} (row {4})").format(
						row.idx, row.item_code, cint(row.day_number), row.meal_type, seen[key]
					)
				)
			seen[key] = row.idx

	def validate_no_overlapping_cycle(self):
		"""Two active cycles covering the same day would make the menu ambiguous.

		Checked on the POS Profile, because that is what the POS override
		resolves the menu by, and on the Branch, because that is the canteen
		a human thinks in.
		"""
		if not (self.is_active and self.from_date and self.to_date):
			return

		for fieldname in ("pos_profile", "branch"):
			value = self.get(fieldname)
			if not value:
				continue

			clash = frappe.get_all(
				"Menu Cycle",
				filters={
					"name": ["!=", self.name or "new"],
					fieldname: value,
					"is_active": 1,
					"from_date": ["<=", self.to_date],
					"to_date": [">=", self.from_date],
				},
				fields=["name", "cycle_name"],
				limit=1,
			)

			if clash:
				frappe.throw(
					_("{0} is already active for {1} over these dates. "
					  "Deactivate it or change the dates.").format(
						frappe.utils.get_link_to_form("Menu Cycle", clash[0].name, clash[0].cycle_name),
						value,
					)
				)

	def validate_consistent_rates(self):
		"""One item can only carry one selling price, so the cycle must agree with itself."""
		rates: dict[tuple[str, str], float] = {}
		for row in self.items:
			if not row.item_code or not flt(row.rate):
				continue

			key = (row.item_code, row.uom or "")
			if key in rates and flt(rates[key]) != flt(row.rate):
				frappe.throw(
					_("Row #{0}: {1} is priced {2} here but {3} elsewhere in this cycle. "
					  "One item can carry only one price per UOM.").format(
						row.idx, row.item_code, flt(row.rate), flt(rates[key])
					)
				)
			rates[key] = flt(row.rate)

	def fill_item_details(self):
		for row in self.items:
			if not row.item_code:
				continue

			item_name, stock_uom = frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom"])
			if not row.item_name:
				row.item_name = item_name
			if not row.uom:
				row.uom = stock_uom

	def sync_menu_rates(self):
		"""The menu drives the price: push each row's rate onto the canteen's selling price list.

		Failures are reported, never fatal - a pricing clash should not stop
		you from planning next week's menu.
		"""
		if not (self.is_active and self.pos_profile):
			return

		price_list = frappe.db.get_value("POS Profile", self.pos_profile, "selling_price_list")
		if not price_list:
			return

		currency = frappe.db.get_value("Price List", price_list, "currency")
		synced, failures = 0, []

		for row in self.items:
			if not row.item_code or not flt(row.rate):
				continue

			try:
				if self.upsert_item_price(row, price_list, currency):
					synced += 1
			except Exception:
				frappe.log_error(
					title=f"Menu Cycle {self.name}: could not price {row.item_code}",
					message=frappe.get_traceback(),
				)
				failures.append(row.item_code)

		if failures:
			frappe.msgprint(
				_("Could not update the price list for: {0}. See the error log for details.").format(
					", ".join(sorted(set(failures)))
				),
				title=_("Menu prices partly synced"),
				indicator="orange",
			)
		elif synced:
			frappe.msgprint(
				_("{0} menu rate(s) written to price list {1}.").format(synced, price_list),
				alert=True,
			)

	def upsert_item_price(self, row, price_list: str, currency: str | None) -> bool:
		"""Point the item's selling price at the menu rate. Returns True if anything changed."""
		uom = row.uom or frappe.db.get_value("Item", row.item_code, "stock_uom")

		existing = frappe.get_all(
			"Item Price",
			filters={"item_code": row.item_code, "price_list": price_list, "uom": uom, "selling": 1},
			fields=["name"],
			order_by="valid_from desc",
			limit=1,
		)

		if existing:
			price = frappe.get_doc("Item Price", existing[0].name)
			if (
				flt(price.price_list_rate) == flt(row.rate)
				and getdate(price.valid_from) == getdate(self.from_date)
				and getdate(price.valid_upto) == getdate(self.to_date)
			):
				return False

			price.price_list_rate = flt(row.rate)
			price.valid_from = self.from_date
			price.valid_upto = self.to_date
			price.save()
			return True

		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": row.item_code,
				"price_list": price_list,
				"uom": uom,
				"selling": 1,
				"currency": currency,
				"price_list_rate": flt(row.rate),
				"valid_from": self.from_date,
				"valid_upto": self.to_date,
			}
		).insert()
		return True
