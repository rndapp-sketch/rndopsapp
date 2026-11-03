# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Create the Acc Head to Head Fund Transfer workflow and list the doctype on the
Pending Tasks page. Until this ran, sites had no h2h_workflow at all: Submit fell
through to a raw docstatus submit, leaving requests "Draft" yet submitted and
outside any approval chain.
"""

from rndopsapp.rndopsapp.create_h2h_workflow import execute as _create_h2h_workflow


def execute():
	_create_h2h_workflow()
