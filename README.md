## Canteen Menu

Menu planning for canteens running on ERPNext Point of Sale.

- **Menu Item Template** - a reusable, named set of dishes that can be pulled into any menu.
- **Menu Cycle** - the live menu for one canteen (POS Profile): the items it sells between **Starts On** and **Until** (leave Until blank and it keeps running). A **Future Planning** table lets you line up the coming weeks; when a window arrives the menu moves onto it by itself.
- **Menu Board** - a desk page showing what a canteen is serving on a given day, priced, and printable.
- **POS integration** - the POS item grid shows *only* what the menu lists at that canteen. Menu rates are pushed to the profile's selling price list, so the menu drives the price.

### Pricing per canteen

Item Price is keyed by price list, so **each canteen wanting its own rates needs its own Price List** on its POS Profile. Two canteens sharing one price list keep only the rate saved last, and both counters charge it. Menu Cycle warns when it spots that - naming the items, the rates and the other canteen - but still saves; whether the canteens should share a price is a menu-planning decision, not something to refuse.

Point a canteen at a price list nothing else uses. A POS Profile sitting on the site's **default** selling price list is warned about, because menu rates are written to that list and would reprice items on quotations, sales orders and invoices too.

### What blocks, and what only warns

Only one thing is refused: the same item listed twice at different rates in one menu, because a price list cannot hold both and one rate would silently vanish. Everything else - an overlapping menu, an active menu with no items, repeated rows, a backwards date range, a shared or default price list - is reported with its consequence and saved anyway.

### Fallbacks

If no active Menu Cycle covers today for a POS Profile, `get_items` delegates to the stock ERPNext implementation and POS behaves exactly as before. Only canteens with a menu are restricted.

### License

MIT
