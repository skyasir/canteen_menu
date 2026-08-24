# Copyright (c) 2026, Yasir Shaikh and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, add_months, flt, getdate, today

from canteen_menu.api import pos
from canteen_menu.menu import get_active_cycle, get_day_number, get_menu_item_codes

try:  # v16
	from frappe.tests import IntegrationTestCase as BaseTestCase
except ImportError:  # v15
	from frappe.tests.utils import FrappeTestCase as BaseTestCase


def get_test_branch() -> str:
	"""A branch of its own, so a real cycle on a real branch never collides."""
	return frappe.get_doc({"doctype": "Branch", "branch": frappe.generate_hash(length=10)}).insert().name


def make_price_list() -> str:
	return frappe.get_doc({
		"doctype": "Price List",
		"price_list_name": frappe.generate_hash(length=10),
		"selling": 1,
		"enabled": 1,
		"currency": frappe.db.get_value("Price List", {"selling": 1}, "currency") or "INR",
	}).insert().name


def make_pos_profile(base: str, price_list: str) -> str:
	"""A counter of its own, cloned from a working profile so POS queries hold up."""
	profile = frappe.copy_doc(frappe.get_doc("POS Profile", base))
	profile.name = frappe.generate_hash(length=10)
	profile.selling_price_list = price_list
	profile.applicable_for_users = []  # a second default for the same user is rejected
	return profile.insert().name


def make_cycle(pos_profile, rows, rotation="Daily", length=7, start=None, active=1, rate=0):
	"""A Menu Cycle starting today, with `rows` as (day_number, item_code) pairs."""
	cycle = frappe.get_doc(
		{
			"doctype": "Menu Cycle",
			"cycle_name": frappe.generate_hash(length=10),
			"branch": get_test_branch(),
			"pos_profile": pos_profile,
			"company": frappe.db.get_value("POS Profile", pos_profile, "company"),
			"rotation_type": rotation,
			"cycle_length": length,
			"is_active": active,
			"from_date": start or today(),
			"to_date": add_days(start or today(), length - 1),
			"items": [
				{"day_number": day, "meal_type": "Lunch", "item_code": item_code, "rate": rate}
				for day, item_code in rows
			],
		}
	)
	cycle.insert()
	return cycle


class TestDayNumber(BaseTestCase):
	"""Rotation maths - no database involved."""

	def cycle(self, rotation, length=7, start="2026-08-01"):
		return frappe._dict(from_date=start, rotation_type=rotation, cycle_length=length)

	def test_daily_rotation_advances_every_day(self):
		cycle = self.cycle("Daily")
		self.assertEqual(get_day_number(cycle, "2026-08-01"), 1)
		self.assertEqual(get_day_number(cycle, "2026-08-04"), 4)

	def test_daily_rotation_wraps_at_cycle_length(self):
		cycle = self.cycle("Daily", length=7)
		self.assertEqual(get_day_number(cycle, "2026-08-08"), 1)
		self.assertEqual(get_day_number(cycle, "2026-08-09"), 2)

	def test_weekly_rotation_advances_every_seven_days(self):
		cycle = self.cycle("Weekly")
		self.assertEqual(get_day_number(cycle, "2026-08-06"), 1)
		self.assertEqual(get_day_number(cycle, "2026-08-08"), 2)
		self.assertEqual(get_day_number(cycle, "2026-08-15"), 3)

	def test_monthly_rotation_advances_every_month(self):
		cycle = self.cycle("Monthly", length=3)
		self.assertEqual(get_day_number(cycle, "2026-08-31"), 1)
		self.assertEqual(get_day_number(cycle, "2026-09-01"), 2)
		self.assertEqual(get_day_number(cycle, "2026-11-01"), 1)

	def test_dates_before_the_cycle_start_are_day_one(self):
		self.assertEqual(get_day_number(self.cycle("Daily"), "2026-07-30"), 1)


class CanteenTestCase(BaseTestCase):
	"""Every test gets a canteen of its own - its own POS Profile on its own
	price list - so real menus on a working site can never interfere.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.base_profile = (frappe.get_all("POS Profile", limit=1, pluck="name") or [None])[0]
		cls.items = frappe.get_all(
			"Item", filters={"disabled": 0, "is_sales_item": 1, "has_variants": 0}, limit=3, pluck="name"
		)

	def setUp(self):
		if not self.base_profile or len(self.items) < 3:
			self.skipTest("needs a POS Profile and at least 3 sellable items")
		self.price_list = make_price_list()
		self.pos_profile = make_pos_profile(self.base_profile, self.price_list)

	def tearDown(self):
		frappe.db.rollback()


class TestMenuResolution(CanteenTestCase):
	def test_only_todays_items_are_on_the_menu(self):
		make_cycle(self.pos_profile, [(1, self.items[0]), (2, self.items[1])])
		self.assertEqual(get_menu_item_codes(self.pos_profile), [self.items[0]])

	def test_day_numbers_must_fit_the_cycle(self):
		with self.assertRaises(frappe.ValidationError):
			make_cycle(self.pos_profile, [(9, self.items[0])], length=7)

	def test_duplicate_rows_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_cycle(self.pos_profile, [(1, self.items[0]), (1, self.items[0])])

	def test_a_cycle_needs_items(self):
		with self.assertRaises(frappe.ValidationError):
			make_cycle(self.pos_profile, [])

	def test_no_cycle_means_no_restriction(self):
		self.assertIsNone(get_menu_item_codes(self.pos_profile))

	def test_inactive_cycle_is_ignored(self):
		make_cycle(self.pos_profile, [(1, self.items[0])], active=0)
		self.assertIsNone(get_menu_item_codes(self.pos_profile))

	def test_cycle_outside_its_dates_is_ignored(self):
		make_cycle(self.pos_profile, [(1, self.items[0])], start=add_months(today(), -6))
		self.assertIsNone(get_active_cycle(self.pos_profile))

	def test_template_rows_never_leak_into_the_menu(self):
		"""Menu Cycle Item is shared with Menu Item Template - parenttype must isolate them."""
		frappe.get_doc(
			{
				"doctype": "Menu Item Template",
				"template_name": frappe.generate_hash(length=10),
				"items": [{"day_number": 1, "meal_type": "Lunch", "item_code": self.items[2]}],
			}
		).insert()

		make_cycle(self.pos_profile, [(1, self.items[0])])

		codes = get_menu_item_codes(self.pos_profile)
		self.assertIn(self.items[0], codes)
		self.assertNotIn(self.items[2], codes)

	def test_overlapping_active_cycles_are_rejected(self):
		make_cycle(self.pos_profile, [(1, self.items[0])])
		with self.assertRaises(frappe.ValidationError):
			make_cycle(self.pos_profile, [(1, self.items[1])])


class TestPOSIntegration(CanteenTestCase):
	def get_items(self, search_term=""):
		result = pos.get_items(
			start=0,
			page_length=100,
			price_list=self.price_list,
			item_group="",
			pos_profile=self.pos_profile,
			search_term=search_term,
		)
		return [item["item_code"] for item in result.get("items", [])]

	def test_pos_shows_the_whole_catalogue_without_a_cycle(self):
		self.assertGreater(len(self.get_items()), 1)

	def test_pos_shows_only_todays_menu(self):
		make_cycle(self.pos_profile, [(1, self.items[0]), (2, self.items[1])])
		self.assertEqual(self.get_items(), [self.items[0]])

	def test_pos_shows_nothing_when_today_has_no_rows(self):
		make_cycle(self.pos_profile, [(2, self.items[0])])
		self.assertEqual(self.get_items(), [])

	def test_search_cannot_reach_past_the_menu(self):
		make_cycle(self.pos_profile, [(1, self.items[0])])
		self.assertEqual(self.get_items(search_term=self.items[1]), [])

	def test_payload_keeps_the_shape_pos_expects(self):
		make_cycle(self.pos_profile, [(1, self.items[0])])
		result = pos.get_items(
			start=0,
			page_length=100,
			price_list=self.price_list,
			item_group="",
			pos_profile=self.pos_profile,
		)
		item = result["items"][0]
		for key in ("item_code", "item_name", "stock_uom", "uom", "actual_qty", "price_list_rate", "currency"):
			self.assertIn(key, item)


class TestMenuPricing(CanteenTestCase):
	"""The menu drives the price: rates land on the canteen's selling price list."""

	def get_price(self, item_code):
		return frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "price_list": self.price_list, "selling": 1},
			["price_list_rate", "valid_from", "valid_upto"],
			as_dict=True,
		)

	def test_menu_rate_reaches_the_price_list(self):
		cycle = make_cycle(self.pos_profile, [(1, self.items[0])], rate=42.5)

		price = self.get_price(self.items[0])
		self.assertIsNotNone(price)
		self.assertEqual(flt(price.price_list_rate), 42.5)
		self.assertEqual(getdate(price.valid_from), getdate(cycle.from_date))
		self.assertEqual(getdate(price.valid_upto), getdate(cycle.to_date))

	def test_changing_the_menu_rate_moves_the_price(self):
		cycle = make_cycle(self.pos_profile, [(1, self.items[0])], rate=42.5)

		cycle.items[0].rate = 55
		cycle.save()

		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 55)

	def test_an_inactive_cycle_does_not_touch_prices(self):
		before = self.get_price(self.items[1])
		make_cycle(self.pos_profile, [(1, self.items[1])], rate=99, active=0)
		self.assertEqual(before, self.get_price(self.items[1]))

	def test_conflicting_rates_in_one_cycle_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Menu Cycle",
					"cycle_name": frappe.generate_hash(length=10),
					"branch": get_test_branch(),
					"pos_profile": self.pos_profile,
					"company": frappe.db.get_value("POS Profile", self.pos_profile, "company"),
					"rotation_type": "Daily",
					"cycle_length": 7,
					"is_active": 1,
					"from_date": today(),
					"to_date": add_days(today(), 6),
					"items": [
						{"day_number": 1, "meal_type": "Lunch", "item_code": self.items[0], "rate": 10},
						{"day_number": 2, "meal_type": "Lunch", "item_code": self.items[0], "rate": 20},
					],
				}
			).insert()

	def test_canteens_sharing_a_price_list_cannot_disagree_on_a_rate(self):
		"""Item Price is keyed by price list, so the second save would overwrite the first."""
		other = make_pos_profile(self.base_profile, self.price_list)
		make_cycle(self.pos_profile, [(1, self.items[0])], rate=40)

		with self.assertRaises(frappe.ValidationError):
			make_cycle(other, [(1, self.items[0])], rate=25)

	def test_canteens_sharing_a_price_list_may_agree_on_a_rate(self):
		other = make_pos_profile(self.base_profile, self.price_list)
		make_cycle(self.pos_profile, [(1, self.items[0])], rate=40)

		make_cycle(other, [(1, self.items[0])], rate=40)  # identical - nothing to overwrite
		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 40)

	def test_separate_price_lists_keep_canteens_independent(self):
		other_list = make_price_list()
		other = make_pos_profile(self.base_profile, other_list)

		make_cycle(self.pos_profile, [(1, self.items[0])], rate=40)
		make_cycle(other, [(1, self.items[0])], rate=25)

		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 40)
		self.assertEqual(
			flt(frappe.db.get_value(
				"Item Price", {"item_code": self.items[0], "price_list": other_list}, "price_list_rate"
			)),
			25,
		)
