## Canteen Menu

Menu planning for canteens running on ERPNext Point of Sale.

- **Menu Item Template** - a reusable, named set of menu rows (a standard breakfast, a week's rotation) that can be pulled into any cycle.
- **Menu Cycle** - the live menu for one canteen (POS Profile) over a date range, rotating daily, weekly or monthly across `cycle_length` days.
- **POS integration** - the POS item grid shows *only* the items scheduled for today at that canteen. Menu rates are pushed to the profile's selling price list, so the menu drives the price.

### How the day is resolved

`from_date` is day 1. For a `Daily` rotation the day number advances every day, `Weekly` every 7 days, `Monthly` every calendar month, and wraps at `cycle_length`. A row with `day_number` 0 (or blank) is served every day of the cycle.

### Fallbacks

If no active Menu Cycle covers today for a POS Profile, `get_items` delegates to the stock ERPNext implementation and POS behaves exactly as before. Only canteens with a menu are restricted.

### License

MIT
