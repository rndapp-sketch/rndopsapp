"""Turns a legacy Excel file into plain JSON rows the frontend can render as a table.

Practically all legacy files are BIFF `.xls`, which no browser can preview and
openpyxl cannot open -- those go through xlrd. The handful of `.xlsx` files go
through openpyxl. Both are already in the bench environment.
"""

import datetime
import os
from io import BytesIO

MAX_SHEETS = 20
MAX_ROWS = 500
MAX_COLS = 40


def _blank(row):
	return all(cell is None or str(cell).strip() == "" for cell in row)


def _trim(rows):
	while rows and _blank(rows[-1]):
		rows.pop()
	return rows


def _finish(rows, max_rows):
	"""Trim trailing blanks, then report whether real content was cut off."""
	rows = _trim(rows)
	truncated = len(rows) > max_rows
	return rows[:max_rows], truncated


def _xls_value(cell, datemode):
	import xlrd

	if cell.ctype == xlrd.XL_CELL_EMPTY or cell.ctype == xlrd.XL_CELL_BLANK:
		return None
	if cell.ctype == xlrd.XL_CELL_ERROR:
		return None
	if cell.ctype == xlrd.XL_CELL_BOOLEAN:
		return bool(cell.value)
	if cell.ctype == xlrd.XL_CELL_DATE:
		try:
			parts = xlrd.xldate_as_tuple(cell.value, datemode)
		except Exception:
			return cell.value
		if parts[:3] == (0, 0, 0):
			return datetime.time(*parts[3:]).isoformat()
		return datetime.datetime(*parts).isoformat(sep=" ")
	if cell.ctype == xlrd.XL_CELL_NUMBER and float(cell.value).is_integer():
		return int(cell.value)
	return cell.value


def _parse_xls(raw, max_rows):
	import xlrd

	book = xlrd.open_workbook(file_contents=raw)
	sheets = []

	for sheet in book.sheets()[:MAX_SHEETS]:
		col_count = min(sheet.ncols, MAX_COLS)
		# sheet.nrows can report the full 65536-row grid on these files, so only
		# ever touch max_rows + 1 rows and let _finish decide about truncation.
		row_count = min(sheet.nrows, max_rows + 1)
		rows = [
			[_xls_value(cell, book.datemode) for cell in sheet.row(index)[:col_count]]
			for index in range(row_count)
		]
		rows, truncated = _finish(rows, max_rows)
		sheets.append({"name": sheet.name, "rows": rows, "truncated": truncated})

	return sheets


def _xlsx_value(value):
	if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
		return value.isoformat(sep=" ") if isinstance(value, datetime.datetime) else value.isoformat()
	return value


def _parse_xlsx(raw, max_rows):
	import openpyxl

	book = openpyxl.load_workbook(BytesIO(raw), read_only=True, data_only=True)
	sheets = []

	try:
		for sheet in book.worksheets[:MAX_SHEETS]:
			rows = [
				[_xlsx_value(value) for value in row]
				for row in sheet.iter_rows(
					max_row=max_rows + 1, max_col=MAX_COLS, values_only=True
				)
			]
			rows, truncated = _finish(rows, max_rows)
			sheets.append({"name": sheet.title, "rows": rows, "truncated": truncated})
	finally:
		book.close()

	return sheets


def parse_workbook(raw, file_name, max_rows=MAX_ROWS):
	"""Return [{name, rows, truncated}] for every sheet in the workbook."""
	extension = os.path.splitext(file_name)[1].lower()
	sheets = _parse_xls(raw, max_rows) if extension == ".xls" else _parse_xlsx(raw, max_rows)

	# Pad every row to the widest one so the frontend can render a rectangular table.
	for sheet in sheets:
		width = max((len(row) for row in sheet["rows"]), default=0)
		sheet["rows"] = [row + [None] * (width - len(row)) for row in sheet["rows"]]
		sheet["column_count"] = width

	return sheets
