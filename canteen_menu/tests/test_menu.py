# Copyright (c) 2026, Yasir Shaikh and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, flt, getdate, today

from canteen_menu.api import pos
from canteen_menu.menu import get_active_cycle, get_menu_item_codes

try:  # v16
	from frappe.tests import IntegrationTestCase as BaseTestCase
except ImportError:  # v15
	from frappe.tests.utils import FrappeTestCase as BaseTestCase


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


def make_cycle(pos_profile, item_codes, start=None, until="", active=1, rate=0, branch=None, schedule=None):
	"""A menu listing `item_codes` for its date range."""
	cycle = frappe.get_doc({
		"doctype": "Menu Cycle",
		"cycle_name": frappe.generate_hash(length=10),
		"branch": branch or make_branch(),
		"pos_profile": pos_profile,
		"company": frappe.db.get_value("POS Profile", pos_profile, "company"),
		"is_active": active,
		"from_date": start or today(),
		"to_date": until,
		"items": [{"item_code": code, "rate": rate} for code in item_codes],
		"schedule": schedule or [],
	})
	cycle.insert()
	return cycle


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

	def messages(self) -> str:
		return " ".join(
			f"{m.get('title', '')} {m.get('message', '')}" for m in (frappe.message_log or [])
		)


class TestMenuResolution(CanteenTestCase):
	def test_the_menu_lists_what_the_counter_sells(self):
		make_cycle(self.pos_profile, [self.items[0], self.items[1]])
		self.assertEqual(get_menu_item_codes(self.pos_profile), sorted(self.items[:2]))

	def test_a_menu_with_no_items_serves_nothing(self):
		make_cycle(self.pos_profile, [])
		self.assertEqual(get_menu_item_codes(self.pos_profile), [])

	def test_no_menu_means_no_restriction(self):
		self.assertIsNone(get_menu_item_codes(self.pos_profile))

	def test_inactive_menu_is_ignored(self):
		make_cycle(self.pos_profile, [self.items[0]], active=0)
		self.assertIsNone(get_menu_item_codes(self.pos_profile))

	def test_a_menu_that_has_ended_is_ignored(self):
		make_cycle(
			self.pos_profile, [self.items[0]],
			start=add_days(today(), -30), until=add_days(today(), -1),
		)
		self.assertIsNone(get_active_cycle(self.pos_profile))

	def test_a_menu_that_has_not_started_is_ignored(self):
		make_cycle(self.pos_profile, [self.items[0]], start=add_days(today(), 7))
		self.assertIsNone(get_active_cycle(self.pos_profile))

	def test_a_blank_end_date_runs_on(self):
		make_cycle(self.pos_profile, [self.items[0]], until="")
		self.assertEqual(get_menu_item_codes(self.pos_profile, add_days(today(), 365)), [self.items[0]])

	def test_template_rows_never_leak_into_the_menu(self):
		"""Menu Cycle Item is shared with Menu Item Template - parenttype must isolate them."""
		frappe.get_doc({
			"doctype": "Menu Item Template",
			"template_name": frappe.generate_hash(length=10),
			"items": [{"item_code": self.items[2]}],
		}).insert()

		make_cycle(self.pos_profile, [self.items[0]])

		codes = get_menu_item_codes(self.pos_profile)
		self.assertIn(self.items[0], codes)
		self.assertNotIn(self.items[2], codes)

	def test_overlapping_active_menus_are_warned_not_blocked(self):
		make_cycle(self.pos_profile, [self.items[0]])

		frappe.local.message_log = []
		second = make_cycle(self.pos_profile, [self.items[1]])

		self.assertTrue(frappe.db.exists("Menu Cycle", second.name), "the save must go through")
		self.assertIn("Another menu overlaps", self.messages())

	def test_duplicate_rows_are_warned_not_blocked(self):
		frappe.local.message_log = []
		cycle = make_cycle(self.pos_profile, [self.items[0], self.items[0]])

		self.assertTrue(frappe.db.exists("Menu Cycle", cycle.name), "the save must go through")
		self.assertIn("Repeated rows", self.messages())

	def test_an_empty_active_menu_is_warned_not_blocked(self):
		frappe.local.message_log = []
		cycle = make_cycle(self.pos_profile, [])

		self.assertTrue(frappe.db.exists("Menu Cycle", cycle.name), "the save must go through")
		self.assertIn("Active menu with no items", self.messages())

	def test_a_backwards_date_range_is_warned_not_blocked(self):
		frappe.local.message_log = []
		cycle = make_cycle(self.pos_profile, [self.items[0]], until=add_days(today(), -5))

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

	def test_pos_shows_only_the_menu(self):
		make_cycle(self.pos_profile, [self.items[0]])
		self.assertEqual(self.get_items(), [self.items[0]])

	def test_pos_shows_nothing_when_the_menu_is_empty(self):
		make_cycle(self.pos_profile, [])
		self.assertEqual(self.get_items(), [])

	def test_search_cannot_reach_past_the_menu(self):
		make_cycle(self.pos_profile, [self.items[0]])
		self.assertEqual(self.get_items(search_term=self.items[1]), [])

	def test_payload_keeps_the_shape_pos_expects(self):
		make_cycle(self.pos_profile, [self.items[0]])
		result = pos.get_items(
			start=0, page_length=100, price_list=self.price_list,
			item_group="", pos_profile=self.pos_profile,
		)
		item = result["items"][0]
		for key in ("item_code", "item_name", "stock_uom", "uom", "actual_qty", "price_list_rate", "currency"):
			self.assertIn(key, item)

	def test_preview_reports_the_live_menu(self):
		cycle = make_cycle(self.pos_profile, [self.items[0]])
		preview = pos.preview_menu(self.pos_profile)

		self.assertEqual(preview["cycle"], cycle.name)
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
		cycle = make_cycle(self.pos_profile, [self.items[0]], rate=42.5, until=add_days(today(), 30))

		price = self.get_price(self.items[0])
		self.assertIsNotNone(price)
		self.assertEqual(flt(price.price_list_rate), 42.5)
		self.assertEqual(getdate(price.valid_from), getdate(cycle.from_date))
		self.assertEqual(getdate(price.valid_upto), getdate(cycle.to_date))

	def test_an_open_ended_menu_prices_without_an_end_date(self):
		make_cycle(self.pos_profile, [self.items[0]], rate=42.5, until="")
		self.assertIsNone(self.get_price(self.items[0]).valid_upto)

	def test_changing_the_menu_rate_moves_the_price(self):
		cycle = make_cycle(self.pos_profile, [self.items[0]], rate=42.5)
		cycle.items[0].rate = 55
		cycle.save()
		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 55)

	def test_an_inactive_menu_does_not_touch_prices(self):
		before = self.get_price(self.items[1])
		make_cycle(self.pos_profile, [self.items[1]], rate=99, active=0)
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
					{"item_code": self.items[0], "rate": 10},
					{"item_code": self.items[0], "rate": 20},
				],
			}).insert()

	def test_canteens_sharing_a_price_list_are_warned_not_blocked(self):
		other = make_pos_profile(self.base_profile, self.price_list)
		make_cycle(self.pos_profile, [self.items[0]], rate=40)

		frappe.local.message_log = []
		cycle = make_cycle(other, [self.items[0]], rate=25)

		self.assertTrue(frappe.db.exists("Menu Cycle", cycle.name), "the save must go through")
		warnings = self.messages()
		self.assertIn("share a price list", warnings)
		self.assertIn(self.items[0], warnings)

	def test_on_a_shared_price_list_the_last_save_wins(self):
		other = make_pos_profile(self.base_profile, self.price_list)
		make_cycle(self.pos_profile, [self.items[0]], rate=40)
		make_cycle(other, [self.items[0]], rate=25)

		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 25)

	def test_separate_price_lists_keep_canteens_independent(self):
		other_list = make_price_list()
		other = make_pos_profile(self.base_profile, other_list)

		make_cycle(self.pos_profile, [self.items[0]], rate=40)
		make_cycle(other, [self.items[0]], rate=25)

		self.assertEqual(flt(self.get_price(self.items[0]).price_list_rate), 40)
		self.assertEqual(flt(self.get_price(self.items[0], other_list).price_list_rate), 25)

	def test_a_menu_on_the_site_default_price_list_is_warned(self):
		default = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		if not default:
			self.skipTest("site has no default selling price list")

		on_default = make_pos_profile(self.base_profile, default)

		frappe.local.message_log = []
		make_cycle(on_default, [self.items[0]], rate=40)

		self.assertIn("default selling price list", self.messages())

	def test_a_menu_on_its_own_price_list_is_not_warned(self):
		frappe.local.message_log = []
		make_cycle(self.pos_profile, [self.items[0]], rate=40)

		self.assertNotIn("default selling price list", self.messages())


class TestScheduledWindows(CanteenTestCase):
	"""Planned weeks: when one arrives, the menu moves onto it."""

	def window(self, start_offset, end_offset):
		return {"from_date": add_days(today(), start_offset), "to_date": add_days(today(), end_offset)}

	def test_the_window_covering_today_goes_live(self):
		cycle = make_cycle(
			self.pos_profile, [self.items[0]],
			start=add_days(today(), -60), until=add_days(today(), -55),
			schedule=[self.window(-3, 3), self.window(10, 16)],
		)

		self.assertEqual(getdate(cycle.from_date), getdate(add_days(today(), -3)))
		self.assertEqual(getdate(cycle.to_date), getdate(add_days(today(), 3)))

	def test_only_the_live_window_is_marked_running_now(self):
		cycle = make_cycle(
			self.pos_profile, [self.items[0]],
			schedule=[self.window(-3, 3), self.window(10, 16)],
		)
		self.assertEqual([row.is_current for row in cycle.schedule], [1, 0])

	def test_a_future_only_schedule_leaves_the_dates_alone(self):
		cycle = make_cycle(
			self.pos_profile, [self.items[0]],
			start=today(), until=add_days(today(), 6),
			schedule=[self.window(30, 36)],
		)
		self.assertEqual(getdate(cycle.from_date), getdate(today()))
		self.assertEqual([row.is_current for row in cycle.schedule], [0])

	def test_overlapping_windows_are_flagged_and_the_first_wins(self):
		frappe.local.message_log = []
		cycle = make_cycle(
			self.pos_profile, [self.items[0]],
			schedule=[self.window(-2, 2), self.window(-1, 5)],
		)

		self.assertIn("Check the planned weeks", self.messages())
		self.assertEqual([row.is_current for row in cycle.schedule], [1, 0])
		self.assertEqual(getdate(cycle.to_date), getdate(add_days(today(), 2)))

	def test_the_daily_job_moves_the_menu_onto_the_new_window(self):
		from unittest.mock import patch

		from canteen_menu import tasks

		cycle = make_cycle(self.pos_profile, [self.items[0]], schedule=[self.window(-3, 3)])
		# rewind the live dates behind the scheduler's back, as if the window
		# had only just come around
		frappe.db.set_value("Menu Cycle", cycle.name, "from_date", add_days(today(), -60),
		                    update_modified=False)
		frappe.db.set_value("Menu Cycle", cycle.name, "to_date", add_days(today(), -55),
		                    update_modified=False)

		with patch.object(frappe.db, "commit"):
			tasks.apply_scheduled_windows()

		moved = frappe.get_doc("Menu Cycle", cycle.name)
		self.assertEqual(getdate(moved.from_date), getdate(add_days(today(), -3)))
		self.assertEqual(moved.schedule[0].is_current, 1)


class TestMenuBoard(CanteenTestCase):
	"""The board must show exactly what the counter will show."""

	def board(self, **kwargs):
		from canteen_menu.api.board import get_menu_board

		return get_menu_board(self.pos_profile, **kwargs)

	def test_the_board_agrees_with_what_pos_serves(self):
		make_cycle(self.pos_profile, [self.items[0], self.items[1]], rate=30)

		data = self.board()
		on_board = sorted(d["item_code"] for d in data["dishes"])

		self.assertEqual(on_board, get_menu_item_codes(self.pos_profile))
		self.assertEqual(data["total_dishes"], 2)

	def test_the_board_reports_the_menu_and_everything_around_it(self):
		cycle = make_cycle(self.pos_profile, [self.items[0]], until=add_days(today(), 6))

		data = self.board()
		self.assertEqual(data["cycle"]["name"], cycle.name)
		self.assertEqual(getdate(data["cycle"]["from_date"]), getdate(cycle.from_date))
		self.assertEqual(getdate(data["cycle"]["to_date"]), getdate(cycle.to_date))
		# the board carries the cycle's own context, not just its items
		for key in ("branch", "company", "pos_profile", "is_active", "cycle_name"):
			self.assertIn(key, data["cycle"])
		self.assertEqual(data["price_list"], self.price_list)

	def test_the_board_lists_the_planned_weeks(self):
		make_cycle(
			self.pos_profile, [self.items[0]],
			schedule=[{"from_date": today(), "to_date": add_days(today(), 6)}],
		)

		windows = self.board()["schedule"]
		self.assertEqual(len(windows), 1)
		self.assertEqual(windows[0]["is_current"], 1)

	def test_a_canteen_with_no_menu_returns_an_empty_board(self):
		data = self.board()
		self.assertIsNone(data["cycle"])
		self.assertEqual(data["dishes"], [])
		self.assertEqual(data["total_dishes"], 0)

	def test_the_board_carries_prices_and_planned_quantities(self):
		make_cycle(self.pos_profile, [self.items[0]], rate=42.5)

		dish = self.board()["dishes"][0]
		self.assertEqual(flt(dish["rate"]), 42.5)
		self.assertIn("item_name", dish)
