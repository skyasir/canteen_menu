# Copyright (c) 2026, Yasir Shaikh and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, flt, getdate, today

from canteen_menu.api import pos
from canteen_menu.menu import WEEKDAYS, get_active_cycle, get_menu_item_codes, get_weekday

try:  # v16
	from frappe.tests import IntegrationTestCase as BaseTestCase
except ImportError:  # v15
	from frappe.tests.utils import FrappeTestCase as BaseTestCase


def next_weekday(weekday: str) -> str:
	return WEEKDAYS[(WEEKDAYS.index(weekday) + 1) % 7]


def make_branch() -> str:
	"""A branch of its own, so a real menu on a real branch never collides."""
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


def make_cycle(pos_profile, rows, start=None, until="", active=1, rate=0, branch=None):
	"""A weekly menu, with `rows` as (weekday, item_code) pairs."""
	cycle = frappe.get_doc({
		"doctype": "Menu Cycle",
		"cycle_name": frappe.generate_hash(length=10),
		"branch": branch or make_branch(),
		"pos_profile": pos_profile,
		"company": frappe.db.get_value("POS Profile", pos_profile, "company"),
		"is_active": active,
		"from_date": start or today(),
		"to_date": until,
		"items": [
			{"weekday": weekday, "meal_type": "Lunch", "item_code": item_code, "rate": rate}
			for weekday, item_code in rows
		],
	})
	cycle.insert()
	return cycle


class TestWeekday(BaseTestCase):
	"""No database, no rotation maths - just the calendar."""

	def test_weekday_names_the_day(self):
		self.assertEqual(get_weekday("2026-08-24"), "Monday")
		self.assertEqual(get_weekday("2026-08-25"), "Tuesday")
		self.assertEqual(get_weekday("2026-08-30"), "Sunday")

	def test_the_week_wraps(self):
		self.assertEqual(get_weekday("2026-08-31"), "Monday")

	def test_next_weekday_helper_wraps(self):
		self.assertEqual(next_weekday("Sunday"), "Monday")


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
		self.today = get_weekday()
		self.tomorrow = next_weekday(self.today)

	def tearDown(self):
		frappe.db.rollback()

	def messages(self) -> str:
		return " ".join(
			f"{m.get('title', '')} {m.get('message', '')}" for m in (frappe.message_log or [])
		)


class TestMenuResolution(CanteenTestCase):
	def test_only_todays_weekday_is_on_the_menu(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0]), (self.tomorrow, self.items[1])])
		self.assertEqual(get_menu_item_codes(self.pos_profile), [self.items[0]])

	def test_a_menu_with_nothing_for_today_serves_nothing(self):
		make_cycle(self.pos_profile, [(self.tomorrow, self.items[0])])
		self.assertEqual(get_menu_item_codes(self.pos_profile), [])

	def test_the_menu_repeats_next_week(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0])], until=add_days(today(), 30))
		self.assertEqual(get_menu_item_codes(self.pos_profile, add_days(today(), 7)), [self.items[0]])
		self.assertEqual(get_menu_item_codes(self.pos_profile, add_days(today(), 1)), [])

	def test_a_blank_end_date_runs_on(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0])], until="")
		# 364 days is exactly 52 weeks, so it lands on the same weekday
		self.assertEqual(get_menu_item_codes(self.pos_profile, add_days(today(), 364)), [self.items[0]])

	def test_no_cycle_means_no_restriction(self):
		self.assertIsNone(get_menu_item_codes(self.pos_profile))

	def test_inactive_cycle_is_ignored(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0])], active=0)
		self.assertIsNone(get_menu_item_codes(self.pos_profile))

	def test_a_menu_that_has_ended_is_ignored(self):
		make_cycle(
			self.pos_profile, [(self.today, self.items[0])],
			start=add_days(today(), -30), until=add_days(today(), -1),
		)
		self.assertIsNone(get_active_cycle(self.pos_profile))

	def test_a_menu_that_has_not_started_is_ignored(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0])], start=add_days(today(), 7))
		self.assertIsNone(get_active_cycle(self.pos_profile))

	def test_template_rows_never_leak_into_the_menu(self):
		"""Menu Cycle Item is shared with Menu Item Template - parenttype must isolate them."""
		frappe.get_doc({
			"doctype": "Menu Item Template",
			"template_name": frappe.generate_hash(length=10),
			"items": [{"weekday": self.today, "meal_type": "Lunch", "item_code": self.items[2]}],
		}).insert()

		make_cycle(self.pos_profile, [(self.today, self.items[0])])

		codes = get_menu_item_codes(self.pos_profile)
		self.assertIn(self.items[0], codes)
		self.assertNotIn(self.items[2], codes)

	def test_overlapping_active_menus_are_warned_not_blocked(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0])])

		frappe.local.message_log = []
		second = make_cycle(self.pos_profile, [(self.today, self.items[1])])

		self.assertTrue(frappe.db.exists("Menu Cycle", second.name), "the save must go through")
		self.assertIn("Another menu overlaps", self.messages())

	def test_an_open_ended_menu_is_reported_against_a_later_one(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0])], until="")

		frappe.local.message_log = []
		make_cycle(self.pos_profile, [(self.today, self.items[1])], start=add_days(today(), 90))

		self.assertIn("Another menu overlaps", self.messages())

	def test_duplicate_rows_are_warned_not_blocked(self):
		frappe.local.message_log = []
		cycle = make_cycle(self.pos_profile, [(self.today, self.items[0]), (self.today, self.items[0])])

		self.assertTrue(frappe.db.exists("Menu Cycle", cycle.name), "the save must go through")
		self.assertIn("Repeated rows", self.messages())

	def test_an_empty_active_menu_is_warned_not_blocked(self):
		frappe.local.message_log = []
		cycle = make_cycle(self.pos_profile, [])

		self.assertTrue(frappe.db.exists("Menu Cycle", cycle.name), "the save must go through")
		self.assertIn("Active menu with no items", self.messages())

	def test_a_backwards_date_range_is_warned_not_blocked(self):
		frappe.local.message_log = []
		cycle = make_cycle(self.pos_profile, [(self.today, self.items[0])], until=add_days(today(), -5))

		self.assertTrue(frappe.db.exists("Menu Cycle", cycle.name), "the save must go through")
		self.assertIn("never runs", self.messages())


class TestPOSIntegration(CanteenTestCase):
	def get_items(self, search_term=""):
		result = pos.get_items(
			start=0, page_length=100, price_list=self.price_list,
			item_group="", pos_profile=self.pos_profile, search_term=search_term,
		)
		return [item["item_code"] for item in result.get("items", [])]

	def test_pos_shows_the_whole_catalogue_without_a_menu(self):
		self.assertGreater(len(self.get_items()), 1)

	def test_pos_shows_only_todays_weekday(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0]), (self.tomorrow, self.items[1])])
		self.assertEqual(self.get_items(), [self.items[0]])

	def test_pos_shows_nothing_when_today_has_no_rows(self):
		make_cycle(self.pos_profile, [(self.tomorrow, self.items[0])])
		self.assertEqual(self.get_items(), [])

	def test_search_cannot_reach_past_the_menu(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0])])
		self.assertEqual(self.get_items(search_term=self.items[1]), [])

	def test_payload_keeps_the_shape_pos_expects(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0])])
		result = pos.get_items(
			start=0, page_length=100, price_list=self.price_list,
			item_group="", pos_profile=self.pos_profile,
		)
		item = result["items"][0]
		for key in ("item_code", "item_name", "stock_uom", "uom", "actual_qty", "price_list_rate", "currency"):
			self.assertIn(key, item)

	def test_preview_reports_the_weekday(self):
		cycle = make_cycle(self.pos_profile, [(self.today, self.items[0])])
		preview = pos.preview_menu(self.pos_profile)
		self.assertEqual(preview["cycle"], cycle.name)
		self.assertEqual(preview["weekday"], self.today)
		self.assertEqual([r["item_code"] for r in preview["items"]], [self.items[0]])


class TestMenuPricing(CanteenTestCase):
	"""The menu drives the price: rates land on the canteen's selling price list."""

	def get_price(self, item_code, price_list=None):
		return frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "price_list": price_list or self.price_list, "selling": 1},
			["price_list_rate", "valid_from", "valid_upto"],
			as_dict=True,
		)

	def test_menu_rate_reaches_the_price_list(self):
		cycle = make_cycle(self.pos_profile, [(self.today, self.items[0])], rate=42.5,
		                   until=add_days(today(), 30))

		price = self.get_price(self.items[0])
		self.assertIsNotNone(price)
		self.assertEqual(flt(price.price_list_rate), 42.5)
		self.assertEqual(getdate(price.valid_from), getdate(cycle.from_date))
		self.assertEqual(getdate(price.valid_upto), getdate(cycle.to_date))

	def test_an_open_ended_menu_prices_without_an_end_date(self):
		make_cycle(self.pos_profile, [(self.today, self.items[0])], rate=42.5, until="")
		self.assertIsNone(self.get_price(self.items[0]).valid_upto)

	def test_changing_the_menu_rate_moves_the_price(self):
		cycle = make_cycle(self.pos_profile, [(self.today, self.items[0])], rate=42.5)
		cycle.items[0].rate = 55
		cycle.save()
		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 55)

	def test_an_inactive_menu_does_not_touch_prices(self):
		before = self.get_price(self.items[1])
		make_cycle(self.pos_profile, [(self.today, self.items[1])], rate=99, active=0)
		self.assertEqual(before, self.get_price(self.items[1]))

	def test_one_item_cannot_carry_two_prices_in_a_menu(self):
		"""A price list holds one rate per item and UOM - the second would vanish."""
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Menu Cycle",
				"cycle_name": frappe.generate_hash(length=10),
				"branch": make_branch(),
				"pos_profile": self.pos_profile,
				"company": frappe.db.get_value("POS Profile", self.pos_profile, "company"),
				"is_active": 1,
				"from_date": today(),
				"items": [
					{"weekday": self.today, "meal_type": "Lunch", "item_code": self.items[0], "rate": 10},
					{"weekday": self.tomorrow, "meal_type": "Lunch", "item_code": self.items[0], "rate": 20},
				],
			}).insert()

	def test_canteens_sharing_a_price_list_are_warned_not_blocked(self):
		other = make_pos_profile(self.base_profile, self.price_list)
		make_cycle(self.pos_profile, [(self.today, self.items[0])], rate=40)

		frappe.local.message_log = []
		cycle = make_cycle(other, [(self.today, self.items[0])], rate=25)

		self.assertTrue(frappe.db.exists("Menu Cycle", cycle.name), "the save must go through")
		warnings = self.messages()
		self.assertIn("share a price list", warnings)
		self.assertIn(self.items[0], warnings)
		self.assertIn(self.price_list, warnings)

	def test_on_a_shared_price_list_the_last_save_wins(self):
		other = make_pos_profile(self.base_profile, self.price_list)
		make_cycle(self.pos_profile, [(self.today, self.items[0])], rate=40)
		make_cycle(other, [(self.today, self.items[0])], rate=25)

		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 25)

	def test_no_warning_when_canteens_agree_on_the_rate(self):
		other = make_pos_profile(self.base_profile, self.price_list)
		make_cycle(self.pos_profile, [(self.today, self.items[0])], rate=40)

		frappe.local.message_log = []
		make_cycle(other, [(self.today, self.items[0])], rate=40)  # identical - nothing to overwrite

		self.assertNotIn("share a price list", self.messages())
		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 40)

	def test_separate_price_lists_keep_canteens_independent(self):
		other_list = make_price_list()
		other = make_pos_profile(self.base_profile, other_list)

		make_cycle(self.pos_profile, [(self.today, self.items[0])], rate=40)
		make_cycle(other, [(self.today, self.items[0])], rate=25)

		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 40)
		self.assertEqual(flt(self.get_price(self.items[0], other_list).price_list_rate), 25)

	def test_a_menu_on_the_site_default_price_list_is_warned(self):
		default = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		if not default:
			self.skipTest("site has no default selling price list")

		on_default = make_pos_profile(self.base_profile, default)

		frappe.local.message_log = []
		make_cycle(on_default, [(self.today, self.items[0])], rate=40)

		self.assertIn("default selling price list", self.messages())

	def test_a_menu_on_its_own_price_list_is_not_warned(self):
		frappe.local.message_log = []
		make_cycle(self.pos_profile, [(self.today, self.items[0])], rate=40)

		self.assertNotIn("default selling price list", self.messages())
