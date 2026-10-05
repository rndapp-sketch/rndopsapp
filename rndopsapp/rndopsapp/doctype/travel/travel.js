// Copyright (c) 2025, rndops and contributors
// For license information, please see license.txt

frappe.ui.form.on("Travel", {

	// -----------------------------------------------------------------------
	// On form refresh / load
	// -----------------------------------------------------------------------
	refresh(frm) {
		// Auto-populate webmail_id_travel on new docs so balance loads correctly
		if (frm.is_new() && !frm.doc.webmail_id_travel) {
			frm.set_value("webmail_id_travel", frappe.session.user);
		}
		_load_scl_balance(frm);
	},

	// -----------------------------------------------------------------------
	// Reload balance when applicant changes (applies when filling for Others)
	// -----------------------------------------------------------------------
	webmail_id_travel(frm) {
		_load_scl_balance(frm);
	},

	// -----------------------------------------------------------------------
	// Project number auto-fill
	// -----------------------------------------------------------------------
	travel_project_title(frm) {
		if (frm.doc.travel_project_title) {
			frappe.db.get_value(
				"Project Registration",
				frm.doc.travel_project_title,
				"project_no",
				(r) => {
					frm.set_value("travel_project_number", r && r.project_no ? r.project_no : "");
				}
			);
		} else {
			frm.set_value("travel_project_number", "");
		}
	},

	// -----------------------------------------------------------------------
	// Reload balance when user toggles SCL requirement
	// -----------------------------------------------------------------------
	travel_special_casual_leave(frm) {
		_load_scl_balance(frm);
		_update_days_warning(frm);
	},

	// -----------------------------------------------------------------------
	// Recalculate days warning when leave dates change
	// -----------------------------------------------------------------------
	travel_leave_from_date(frm) {
		_update_days_warning(frm);
	},
	travel_leave_to_date(frm) {
		_update_days_warning(frm);
	},
});


// ---------------------------------------------------------------------------
// Fetch SCL balance from backend and render into travel_leave_balance_html
// ---------------------------------------------------------------------------
function _load_scl_balance(frm) {
	// Prefer the applicant set on the form; fall back to logged-in user
	const employee = frm.doc.webmail_id_travel || frappe.session.user;
	console.log("[SCL] Loading balance for:", employee);

	frappe.call({
		method: "rndopsapp.rndopsapp.doctype.travel.travel.get_special_leave_balance_for_travel",
		args: { employee },
		callback(r) {
			if (r.exc || !r.message) {
				_render_balance_html(frm, null);
				return;
			}
			_render_balance_html(frm, r.message);
			_update_days_warning(frm, r.message);
		},
	});
}


// ---------------------------------------------------------------------------
// Render the HTML balance card
// ---------------------------------------------------------------------------
function _render_balance_html(frm, data) {
	let html = "";

	if (!data) {
		html = `
		<div style="border:1px solid #d1d8dd;padding:12px;border-radius:6px;background:#fff8f0;">
			<strong>Special Casual Leave (SCL)</strong><br>
			<span style="color:#888;">Unable to load balance. Please refresh.</span>
		</div>`;
	} else if (!data.is_eligible) {
		html = `
		<div style="border:1px solid #d1d8dd;padding:12px;border-radius:6px;background:#f9f9f9;">
			<strong>Special Casual Leave (SCL)</strong><br>
			<span style="color:#888;">Not eligible for SCL.</span>
		</div>`;
	} else {
		const available = data.available_balance || 0;
		const color = available > 0 ? "#1a7f37" : "#cf1322";
		const icon = available > 0 ? "✅" : "⚠️";

		html = `
		<div style="border:1px solid #d1d8dd;padding:12px;border-radius:6px;background:#fff;">
			<strong style="font-size:14px;">Special Casual Leave (SCL) — ${data.year}</strong>
			<table style="margin-top:8px;width:100%;border-collapse:collapse;font-size:13px;">
				<tr>
					<td style="padding:2px 8px 2px 0;color:#555;">Total Credited</td>
					<td style="padding:2px 0;font-weight:600;">${data.total_credited} days</td>
				</tr>
				<tr>
					<td style="padding:2px 8px 2px 0;color:#555;">Utilized</td>
					<td style="padding:2px 0;font-weight:600;">${data.utilized_balance} days</td>
				</tr>
				<tr>
					<td style="padding:2px 8px 2px 0;color:#555;">Available</td>
					<td style="padding:2px 0;font-weight:700;color:${color};">${available} days ${icon}</td>
				</tr>
			</table>
			${available === 0
				? `<div style="margin-top:8px;padding:6px 10px;background:#fff1f0;border-radius:4px;color:#cf1322;font-size:12px;">
					You have exhausted your SCL quota for ${data.year}.
				   </div>`
				: ""}
		</div>`;
	}

	frm.get_field("travel_leave_balance_html").$wrapper.html(html);
}


// ---------------------------------------------------------------------------
// Inline days-requested warning below the leave date fields
// ---------------------------------------------------------------------------
function _update_days_warning(frm, balanceData) {
	// Only show warning when SCL is Required
	if (frm.doc.travel_special_casual_leave !== "Required") {
		_clear_days_warning(frm);
		return;
	}

	const from = frm.doc.travel_leave_from_date;
	const to = frm.doc.travel_leave_to_date;

	if (!from || !to) {
		_clear_days_warning(frm);
		return;
	}

	const days = Math.max(0, frappe.datetime.get_day_diff(to, from) + 1);

	if (days <= 0) {
		_clear_days_warning(frm);
		return;
	}

	// If we already have the balance data, render immediately
	if (balanceData !== undefined) {
		_render_days_warning(frm, days, balanceData);
		return;
	}

	// Otherwise fetch first
	const employee = frm.doc.webmail_id_travel || frappe.session.user;
	frappe.call({
		method: "rndopsapp.rndopsapp.doctype.travel.travel.get_special_leave_balance_for_travel",
		args: { employee },
		callback(r) {
			_render_days_warning(frm, days, r.message || null);
		},
	});
}


function _render_days_warning(frm, days, data) {
	const available = data ? (data.available_balance || 0) : null;
	const over = available !== null && days > available;

	let msg = `You are requesting <strong>${days} day(s)</strong> of Special Casual Leave.`;
	if (available !== null) {
		msg += ` Available balance: <strong>${available} day(s)</strong>.`;
	}

	let bg = "#e6f4ff";
	let color = "#0958d9";
	let icon = "ℹ️";

	if (over) {
		bg = "#fff1f0";
		color = "#cf1322";
		icon = "⚠️";
		msg += ` <strong>This exceeds your available balance!</strong>`;
	}

	const $field = frm.get_field("travel_leave_to_date");
	if (!$field) return;

	// Attach a small div below the To-Date field
	$field.$wrapper.find(".scl-days-warning").remove();
	$field.$wrapper.append(
		`<div class="scl-days-warning" style="
			margin-top:6px;padding:6px 10px;
			background:${bg};border-radius:4px;
			color:${color};font-size:12px;line-height:1.5;">
			${icon} ${msg}
		</div>`
	);
}


function _clear_days_warning(frm) {
	const $field = frm.get_field("travel_leave_to_date");
	if ($field) $field.$wrapper.find(".scl-days-warning").remove();
}