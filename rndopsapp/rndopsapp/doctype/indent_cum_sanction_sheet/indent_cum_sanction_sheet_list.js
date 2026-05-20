frappe.listview_settings["Indent Cum Sanction Sheet"] = {
	add_fields: ["workflow_state"],
	has_indicator_for_draft: true,
	has_indicator_for_cancelled: true,
	get_indicator(doc) {
		const state = doc.workflow_state || "Draft";
		const color = {
			Draft: "gray",
			Approved: "green",
			Rejected: "red",
		}[state] || "blue";

		return [state, color, `workflow_state,=,${state}`];
	},
};
