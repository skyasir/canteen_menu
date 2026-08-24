"""Point of Sale item grid, restricted to today's canteen menu.

`erpnext.selling.page.point_of_sale.point_of_sale.get_items` is overridden
via `override_whitelisted_methods`; pos_item_selector.js calls it by name, so
the swap is invisible to the POS UI.

When the POS Profile has no active Menu Cycle we hand the call straight back
to ERPNext, so a counter without a menu behaves exactly as stock POS. When a
menu is running, the item query below mirrors ERPNext 16.x `get_items` with
one extra condition - `Item.name in (today's menu)` - and returns the same
payload shape the UI expects.
"""

import frappe
from frappe.query_builder import Order
from frappe.utils import cint
from frappe.utils.nestedset import get_root_of

from erpnext.accounts.doctype.pos_invoice.pos_invoice import get_stock_availability
from erpnext.selling.page.point_of_sale.point_of_sale import (
	filter_result_items,
	get_conditions,
	get_item_group_condition,
	search_by_term,
)
from erpnext.selling.page.point_of_sale.point_of_sale import get_items as erpnext_get_items
from erpnext.stock.get_item_details import get_conversion_factor

from canteen_menu.menu import get_active_cycle, get_day_number, get_menu_item_codes, get_menu_rows


@frappe.whitelist()
def get_items(start, page_length, price_list, item_group, pos_profile, search_term=""):
	allowed_items = get_menu_item_codes(pos_profile)

	if allowed_items is None:
		# No menu for this canteen today - stock ERPNext behaviour.
		return erpnext_get_items(start, page_length, price_list, item_group, pos_profile, search_term)

	if not allowed_items:
		# A menu is running but nothing is scheduled today. Deliberately empty.
		return {"items": []}

	return _get_menu_items(
		start, page_length, price_list, item_group, pos_profile, search_term, allowed_items
	)


def _get_menu_items(start, page_length, price_list, item_group, pos_profile, search_term, allowed_items):
	warehouse, hide_unavailable_items = frappe.db.get_value(
		"POS Profile", pos_profile, ["warehouse", "hide_unavailable_items"]
	)

	result = []

	if search_term:
		# Barcode / serial / batch scans still work, but only for menu items.
		scanned = search_by_term(search_term, warehouse, price_list) or {}
		filter_result_items(scanned, pos_profile)
		if scanned.get("items"):
			# A scan that resolves to an off-menu item returns nothing rather
			# than falling through to a name search.
			return {
				"items": [
					item for item in scanned["items"] if item.get("item_code") in allowed_items
				]
			}

	if not frappe.db.exists("Item Group", item_group):
		item_group = get_root_of("Item Group")

	lft, rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"])

	item = frappe.qb.DocType("Item")
	item_group_dt = frappe.qb.DocType("Item Group")

	item_group_subquery = (
		frappe.qb.from_(item_group_dt)
		.select(item_group_dt.name)
		.where((item_group_dt.lft >= lft) & (item_group_dt.rgt <= rgt))
	)

	query = (
		frappe.qb.from_(item)
		.select(
			item.name.as_("item_code"),
			item.item_name,
			item.description,
			item.stock_uom,
			item.image.as_("item_image"),
			item.is_stock_item,
			item.sales_uom,
		)
		.where(
			(item.disabled == 0)
			& (item.has_variants == 0)
			& (item.is_sales_item == 1)
			& (item.is_fixed_asset == 0)
			& (item.item_group.isin(item_group_subquery))
			& (item.name.isin(allowed_items))
			& get_conditions(search_term, item)
		)
	)

	item_group_condition = get_item_group_condition(pos_profile, item)
	if item_group_condition is not None:
		query = query.where(item_group_condition)

	if hide_unavailable_items:
		bin_dt = frappe.qb.DocType("Bin")
		query = (
			query.left_join(bin_dt)
			.on(bin_dt.item_code == item.name)
			.where(
				(item.is_stock_item == 0)
				| ((item.is_stock_item == 1) & (bin_dt.warehouse == warehouse) & (bin_dt.actual_qty > 0))
			)
		)

	items_data = (
		query.orderby(item.name, order=Order.asc).limit(cint(page_length)).offset(cint(start)).run(as_dict=1)
	)

	if not items_data:
		return {"items": []}

	current_date = frappe.utils.today()

	for item in items_data:
		item.actual_qty, _, _ = get_stock_availability(item.item_code, warehouse)

		item_price = frappe.qb.DocType("Item Price")
		item_prices = (
			frappe.qb.from_(item_price)
			.select(
				item_price.price_list_rate,
				item_price.currency,
				item_price.uom,
				item_price.batch_no,
				item_price.valid_from,
				item_price.valid_upto,
			)
			.where(item_price.price_list == price_list)
			.where(item_price.item_code == item.item_code)
			.where(item_price.selling == 1)
			.where((item_price.valid_from <= current_date) | (item_price.valid_from.isnull()))
			.where((item_price.valid_upto >= current_date) | (item_price.valid_upto.isnull()))
			.orderby(item_price.valid_from, order=Order.desc)
		).run(as_dict=True)

		stock_uom_price = next((d for d in item_prices if d.get("uom") == item.stock_uom), {})
		item_uom = item.stock_uom
		item_uom_price = stock_uom_price

		if item.sales_uom and item.sales_uom != item.stock_uom:
			item_uom = item.sales_uom
			sales_uom_price = next((d for d in item_prices if d.get("uom") == item.sales_uom), {})
			if sales_uom_price:
				item_uom_price = sales_uom_price

		if item_prices and not item_uom_price:
			item_uom = item_prices[0].get("uom")
			item_uom_price = item_prices[0]

		conversion_factor = get_conversion_factor(item.item_code, item_uom).get("conversion_factor")

		if item.stock_uom != item_uom:
			item.actual_qty = item.actual_qty // conversion_factor

		if item_uom_price and item_uom != item_uom_price.get("uom"):
			item_uom_price.price_list_rate = item_uom_price.price_list_rate * conversion_factor

		result.append(
			{
				**item,
				"price_list_rate": item_uom_price.get("price_list_rate"),
				"currency": item_uom_price.get("currency"),
				"uom": item_uom,
				"batch_no": item_uom_price.get("batch_no"),
			}
		)

	return {"items": result}


@frappe.whitelist()
def preview_menu(pos_profile: str, on_date: str | None = None) -> dict:
	"""What POS will show at this canteen on `on_date`. Used by the desk button."""
	frappe.has_permission("Menu Cycle", throw=True)

	cycle = get_active_cycle(pos_profile, on_date)
	if not cycle:
		return {"cycle": None, "day_number": None, "items": []}

	return {
		"cycle": cycle.name,
		"day_number": get_day_number(cycle, on_date),
		"items": get_menu_rows(pos_profile, on_date),
	}
