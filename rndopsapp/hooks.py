app_name = "rndopsapp"
app_title = "Rndopsapp"
app_publisher = "rndops"
app_description = "RND automation software"
app_email = "okjimmy@rnd.iitg.ac.in"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "rndopsapp",
# 		"logo": "/assets/rndopsapp/logo.png",
# 		"title": "Rndopsapp",
# 		"route": "/rndopsapp",
# 		"has_permission": "rndopsapp.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/rndopsapp/css/rndopsapp.css"
# app_include_js = "/assets/rndopsapp/js/rndopsapp.js"

# include js, css files in header of web template
# web_include_css = "/assets/rndopsapp/css/rndopsapp.css"
# web_include_js = "/assets/rndopsapp/js/rndopsapp.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "rndopsapp/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "rndopsapp/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "rndopsapp.utils.jinja_methods",
# 	"filters": "rndopsapp.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "rndopsapp.install.before_install"
# after_install = "rndopsapp.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "rndopsapp.uninstall.before_uninstall"
# after_uninstall = "rndopsapp.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "rndopsapp.utils.before_app_install"
# after_app_install = "rndopsapp.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "rndopsapp.utils.before_app_uninstall"
# after_app_uninstall = "rndopsapp.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "rndopsapp.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

_DU = "rndopsapp.rndopsapp.delegate_user.delegate_user"

permission_query_conditions = {
	"Project Registration":          f"{_DU}.project_registration_permission_query",
	"Travel":                        f"{_DU}.travel_permission_query",
	"TA DA Settlement":              f"{_DU}.ta_da_settlement_permission_query",
	"Temporary Advance":             f"{_DU}.temporary_advance_permission_query",
	"Advance Settlement":            f"{_DU}.advance_settlement_permission_query",
	"Reimbursement":                 f"{_DU}.reimbursement_permission_query",
	"Direct Purchase":               f"{_DU}.direct_purchase_permission_query",
	"Disbursal of Consultancy":      f"{_DU}.disbursal_of_consultancy_permission_query",
	"Disbursal of Honorarium":       f"{_DU}.disbursal_of_honorarium_permission_query",
	"Loan Request":                  f"{_DU}.loan_request_permission_query",
	"Indent General Form":           f"{_DU}.indent_general_form_permission_query",
	"Indent Cum Sanction Sheet":     f"{_DU}.indent_cum_sanction_sheet_permission_query",
	"Recruitment Adhoc Contractual": f"{_DU}.recruitment_adhoc_contractual_permission_query",
}

# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"*": {
		"on_update": [
			"rndopsapp.rndopsapp.commitPayment.check_workflow_and_publish",
			"rndopsapp.rndopsapp.activity_logger.log_workflow_transition",
			"rndopsapp.external_auth.log_impersonated_action",
		],
		"after_insert": ["rndopsapp.external_auth.log_impersonated_action"],
		"on_submit": ["rndopsapp.external_auth.log_impersonated_action"],
		"on_cancel": ["rndopsapp.external_auth.log_impersonated_action"],
		"on_trash": ["rndopsapp.external_auth.log_impersonated_action"],
	}
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"rndopsapp.rndopsapp.api.auto_clear_old_mattermost_posts"
	],
	"cron": {
		# SCL January credit — Jan 1 at midnight (creates new-year record, credits 15 days)
		"0 0 1 1 *": [
			"rndopsapp.rndopsapp.tasks.scl_credit.credit_january_scl"
		],
		# SCL July credit — Jul 1 at midnight (adds 15 days, total becomes 30)
		"0 0 1 7 *": [
			"rndopsapp.rndopsapp.tasks.scl_credit.credit_july_scl"
		],
	},
}

# Testing
# -------

# before_tests = "rndopsapp.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "rndopsapp.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "rndopsapp.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
before_request = [
	"rndopsapp.rndopsapp.doctype.project_verification.project_verification.restrict_verification_staff_routes",
]
before_login = [
	"rndopsapp.external_auth.clear_admin_ip_lock",
	"rndopsapp.external_auth.patch_find_by_credentials",
]
on_logout = ["rndopsapp.external_auth.log_admin_logout"]
# after_request = ["rndopsapp.utils.after_request"]

# Job Events
# ----------
# before_job = ["rndopsapp.utils.before_job"]
# after_job = ["rndopsapp.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"rndopsapp.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }


website_route_rules = [{'from_route': '/frontend/<path:app_path>', 'to_route': 'frontend'},]

