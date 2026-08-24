## Canteen Menu

Menu planning for canteens running on ERPNext Point of Sale.

- **Menu Item Template** - a reusable, named set of menu rows (a standard week, a festival menu) that can be pulled into any menu.
- **Menu Cycle** - the live weekly menu for one canteen (POS Profile). Each row names the **weekday** it is served on, and the menu repeats every week from **Starts On** until **Until** (leave blank and it just keeps running).
- **POS integration** - the POS item grid shows *only* the items scheduled for today's weekday at that canteen. Menu rates are pushed to the profile's selling price list, so the menu drives the price.

### Pricing per canteen

Item Price is keyed by price list, so **each canteen needs its own Price List** on its POS Profile. Two canteens sharing one price list would overwrite each other's rates; Menu Cycle refuses to save when that would happen and names the price list to split.

### Fallbacks

If no active Menu Cycle covers today for a POS Profile, `get_items` delegates to the stock ERPNext implementation and POS behaves exactly as before. Only canteens with a menu are restricted.

### Upgrading from 0.1.x

0.1.x described menus as "Rotation" + "Cycle Length (Days)" + a numeric "Day No" per row. 0.2.0 replaces all three with a weekday on each row. The patch `convert_day_numbers_to_weekdays` maps existing rows: Day 1 becomes the weekday the cycle's `from_date` falls on, Day 2 the next day, and so on. Template rows, which have no start date, take Day 1 as Monday.

### License

MIT
