# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json
import os

import frappe
from frappe.utils import add_days, getdate


def _get_holiday_dates(year):
	"""Return the set of holiday date strings (YYYY-MM-DD) for `year` from the
	institute calendar at rndopsapp/calender/<year>/calender.json. Returns an
	empty set (weekends-only) if no calendar file has been uploaded for that
	year, since future-year calendars may not exist yet at the time an
	extension is processed."""
	path = frappe.get_app_path("rndopsapp", "rndopsapp", "calender", str(year), "calender.json")
	if not os.path.exists(path):
		return set()

	with open(path) as f:
		data = json.load(f)

	holidays = set()
	for month in data.get("calendar", {}).get("months", []):
		for day in month.get("days", []):
			if day.get("holiday"):
				holidays.add(day["date"])
	return holidays


def is_working_day(date):
	"""A day is a working day unless it falls on a Saturday/Sunday or is
	listed as a holiday in that year's institute calendar."""
	date = getdate(date)
	if date.weekday() >= 5:  # Saturday=5, Sunday=6
		return False
	return date.isoformat() not in _get_holiday_dates(date.year)


def add_working_days(start_date, n):
	"""Return the date that is `n` working days after `start_date`, skipping
	weekends and institute holidays."""
	date = getdate(start_date)
	counted = 0
	while counted < n:
		date = add_days(date, 1)
		if is_working_day(date):
			counted += 1
	return date
