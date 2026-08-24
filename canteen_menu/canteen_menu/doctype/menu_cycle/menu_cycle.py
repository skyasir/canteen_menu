# Copyright (c) 2026, Yasir Shaikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


def same_date(a, b) -> bool:
	"""Date equality that treats blank as blank, not as today."""
	return (getdate(a) if a else None) == (getdate(b) if b else None)


class MenuCycle(Document):
	def validate(self):
		self.validate_dates()
		self.validate_items_present()
		# Fills in UOM, which the rate comparisons below key on - must run first.
		self.fill_item_details()
		self.validate_unique_rows()
		self.validate_no_overlapping_cycle()
		self.validate_consistent_rates()
		self.warn_if_price_list_is_the_site_default()
		self.warn_if_price_list_shared()

	def on_update(self):
		self.sync_menu_rates()

	def validate_dates(self):
		if self.to_date and getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("Until cannot be before Starts On"))

	def validate_items_present(self):
		if not self.items:
			frappe.throw(_("Add at least one menu item"))

	def validate_unique_rows(self):
		seen: dict[tuple, int] = {}
		for row in self.items:
			key = (row.weekday, row.meal_type, row.item_code)
			if key in seen:
				frappe.throw(
					_("Row #{0}: {1} is already listed for {2} {3} (row {4})").format(
						row.idx, row.item_code, row.weekday, row.meal_type, seen[key]
					)
				)
			seen[key] = row.idx

	def overlapping_active_cycles(self, *conditions) -> list[frappe._dict]:
		"""Other active cycles whose run overlaps this one's.

		A blank `to_date` on either side means "no end", so the overlap test
		has to treat it as open rather than as a date.
		"""
		cycle = frappe.qb.DocType("Menu Cycle")

		query = (
			frappe.qb.from_(cycle)
			.select(cycle.name, cycle.cycle_name, cycle.pos_profile)
			.where(
				(cycle.name != (self.name or "new"))
				& (cycle.is_active == 1)
				& (cycle.to_date.isnull() | (cycle.to_date >= self.from_date))
			)
		)

		if self.to_date:
			query = query.where(cycle.from_date <= self.to_date)

		for condition in conditions:
			query = query.where(condition)

		return query.run(as_dict=True)

	def validate_no_overlapping_cycle(self):
		"""Two active cycles covering the same day would make the menu ambiguous.

		Checked on the POS Profile, because that is what the POS override
		resolves the menu by, and on the Branch, because that is the canteen
		a human thinks in.
		"""
		if not (self.is_active and self.from_date):
			return

		cycle = frappe.qb.DocType("Menu Cycle")

		for fieldname in ("pos_profile", "branch"):
			value = self.get(fieldname)
			if not value:
				continue

			clash = self.overlapping_active_cycles(cycle[fieldname] == value)
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
					_("Row #{0}: {1} is priced {2} here but {3} elsewhere in this menu. "
					  "One item can carry only one price per UOM.").format(
						row.idx, row.item_code, flt(row.rate), flt(rates[key])
					)
				)
			rates[key] = flt(row.rate)

	def warn_if_price_list_is_the_site_default(self):
		"""A canteen on the default price list rewrites everyone's selling prices.

		Menu rates are pushed onto the POS Profile's price list. If that is the
		site's default, every quotation, sales order and invoice reads the same
		list, and a menu row for an item sold elsewhere silently reprices it.
		"""
		if not (self.is_active and self.pos_profile):
			return

		price_list = frappe.db.get_value("POS Profile", self.pos_profile, "selling_price_list")
		if not price_list or price_list != frappe.db.get_single_value("Selling Settings", "selling_price_list"):
			return

		frappe.msgprint(
			_("{0} sells on {1}, which is this site's default selling price list. Menu rates are "
			  "written to it, so a menu row for an item you also sell elsewhere will reprice it on "
			  "quotations, sales orders and invoices too. Give {0} its own Price List on its POS "
			  "Profile to keep the menu to itself.").format(self.pos_profile, price_list),
			title=_("Menu is pricing into the default price list"),
			indicator="orange",
		)

	def warn_if_price_list_shared(self):
		"""Flag - but do not block - two canteens pricing one item differently.

		Item Price is keyed by price list, not by counter, so when two canteens
		sell through one price list only the rate saved last survives and both
		counters charge it. That is a decision for whoever is planning the menu,
		not something to refuse, so this warns and gets out of the way.
		"""
		if not (self.is_active and self.pos_profile and self.from_date):
			return

		price_list = frappe.db.get_value("POS Profile", self.pos_profile, "selling_price_list")
		if not price_list:
			return

		my_rates = {
			(row.item_code, row.uom or ""): flt(row.rate)
			for row in self.items
			if row.item_code and flt(row.rate)
		}
		if not my_rates:
			return

		cycle = frappe.qb.DocType("Menu Cycle")
		# "!=" also drops rows with no POS Profile, which cannot reach a till anyway.
		others = self.overlapping_active_cycles(cycle.pos_profile != self.pos_profile)

		# Keyed by item, since the other menu may serve it on several weekdays
		# and we only want to say it once.
		clashes: dict[tuple[str, str], str] = {}
		for other in others:
			if frappe.db.get_value("POS Profile", other.pos_profile, "selling_price_list") != price_list:
				continue

			for row in frappe.get_all(
				"Menu Cycle Item",
				filters={"parenttype": "Menu Cycle", "parent": other.name},
				fields=["item_code", "uom", "rate"],
			):
				key = (row.item_code, row.uom or "")
				if not (flt(row.rate) and key in my_rates and flt(row.rate) != my_rates[key]):
					continue

				clashes[key] = (
					_("{0} - {1} here, {2} at {3} ({4})").format(
						row.item_code,
						flt(my_rates[key]),
						flt(row.rate),
						other.pos_profile,
						frappe.utils.get_link_to_form("Menu Cycle", other.name, other.cycle_name),
					)
				)

		if not clashes:
			return

		frappe.msgprint(
			_("{0} shares price list {1} with another canteen, and these rates disagree:").format(
				self.pos_profile, price_list
			)
			+ "<ul><li>"
			+ "</li><li>".join(clashes.values())
			+ "</li></ul>"
			+ _("Saving anyway is fine - but {0} keeps whichever rate was saved last, so both "
			    "counters will charge it. To price independently, give {1} its own Price List "
			    "on its POS Profile.").format(price_list, self.pos_profile),
			title=_("Canteens share a price list"),
			indicator="orange",
		)

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
				and same_date(price.valid_from, self.from_date)
				and same_date(price.valid_upto, self.to_date)
			):
				return False

			price.price_list_rate = flt(row.rate)
			price.valid_from = self.from_date
			price.valid_upto = self.to_date or None
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
				"valid_upto": self.to_date or None,
			}
		).insert()
		return True
