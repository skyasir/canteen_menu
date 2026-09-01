app_name = "canteen_menu"
app_title = "Canteen Menu"
app_publisher = "Yasir Shaikh"
app_description = (
	"Canteen menu cycles for ERPNext - plan a rotating menu per canteen "
	"and expose only today's menu items in Point of Sale"
)
app_email = "erp.yasirshaikh@gmail.com"
app_license = "mit"

required_apps = ["frappe/erpnext"]

add_to_apps_screen = [
	{
		"name": app_name,
		"logo": "/assets/canteen_menu/images/canteen-menu-logo.svg",
		"title": app_title,
		"route": "/desk/canteen-menu",
		"has_permission": "canteen_menu.permissions.check_app_permission",
	}
]

# Point of Sale shows only the items on today's menu for the canteen behind
# the POS Profile. Falls back to stock behaviour when no Menu Cycle is active.
after_install = "canteen_menu.install.after_install"

scheduler_events = {
	"daily": [
		"canteen_menu.tasks.apply_scheduled_windows",
	],
}

override_whitelisted_methods = {
	"erpnext.selling.page.point_of_sale.point_of_sale.get_items": "canteen_menu.api.pos.get_items",
}
