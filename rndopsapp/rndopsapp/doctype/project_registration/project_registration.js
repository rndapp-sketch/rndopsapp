// Copyright (c) 2025, rndops and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Project Registration", {
// 	refresh(frm) {

// 	},
// });

// =========================v1
// frappe.ui.form.on('Project Registration', {
//     refresh: function(frm) {
//         // Hide default workflow buttons
//         frm.page.clear_actions();

//         // Show custom buttons ONLY if current user is the assigned head approver
//         frm.clear_custom_buttons();
//         if (frm.doc.workflow_state === "Pending HoD Approval" && frappe.session.user === frm.doc.head_approver) {
//             ["Approve", "Reject", "Cancel"].forEach(action => {
//                 frm.add_custom_button(action, () => {
//                     frappe.call({
//                         method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.handle_action",
//                         args: {
//                             docname: frm.doc.name,
//                             action: action
//                         },
//                         callback: function(r) {
//                             if (!r.exc) frm.reload_doc();
//                         }
//                     });
//                 }, "Actions");
//             });
//         }

//     }
// });

// ===================================v2-=-=-=-=-=-= working code
// frappe.ui.form.on('Project Registration', {
//     refresh: function(frm) {
//         // Hide default workflow buttons
//         frm.page.clear_actions();
//         frm.clear_custom_buttons();

//         const state = frm.doc.workflow_state;
//         const current_user = frappe.session.user;

//         // Helper: Attach action buttons dynamically
//         function add_action_buttons(actions) {
//             actions.forEach(action => {
//                 frm.add_custom_button(action, () => {
//                     frappe.call({
//                         method: "rndopsapp.rndopsapp.api.handle_approval_action",
//                         args: {
//                             docname: frm.doc.name,
//                             action: action
//                         },
//                         callback: function(r) {
//                             if (!r.exc) frm.reload_doc();
//                         }
//                     });
//                 }, "Actions");
//             });
//         }
//         console.log(" frappe.user:", frappe.user)
//         console.log("User roles:", frappe.user_roles);
//         // --- Workflow Logic ---
//         if (state === "Pending HoD Approval" && current_user === frm.doc.head_approver) {
//             add_action_buttons(["Approve", "Reject", "Put Back"]);
//         }

//         else if (state === "Pending Staff Approval" && frappe.user.has_role("staff, RnD")) {
//             add_action_buttons(["Approve", "Reject", "Put Back"]);
//         }

//         else if (state === "Pending HoS Approval" && frappe.user.has_role("Hos, RnD (Head of Section, RnD)")) {
//             add_action_buttons(["Approve", "Reject", "Put Back"]);
//         }

//         else if (state === "Pending Dean Approval" && frappe.user.has_role("Dean, RnD")) {
//             add_action_buttons(["Approve", "Reject", "Put Back"]);
//         }

//         else if (state === "Needs Correction" && current_user === frm.doc.owner) {
//             add_action_buttons(["Resubmit"]);
//         }

//         // Optional: For System Manager or devs
//         else if (frappe.user.has_role("System Manager")) {
//             frm.add_custom_button("Force Approve", () => {
//                 frappe.call({
//                     method: "rndopsapp.rndopsapp.api.handle_approval_action",
//                     args: {
//                         docname: frm.doc.name,
//                         action: "Approve"
//                     },
//                     callback: function(r) {
//                         if (!r.exc) frm.reload_doc();
//                     }
//                 });
//             }, "Admin Actions");
//         }
//     }
// });

// // -=-=-=-=-=-=-=-=working version below
// frappe.ui.form.on('Project Registration', {
//     refresh: function(frm) {
//         // Hide default workflow buttons
//         frm.page.clear_actions();
//         frm.clear_custom_buttons();

//         if (frm.is_new()) return;

//         frappe.call({
//             method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_available_workflow_actions",
//             args: {
//                 docname: frm.doc.name
//             },
//             callback: function(r) {
//                 const actions = r.message || [];
//                 console.log("🔄 Available Workflow Actions:", actions);

//                 if (actions.length > 0) {
//                     actions.forEach(action => {
//                         frm.add_custom_button(action, function () {
//                             frappe.confirm(
//                                 `Are you sure you want to perform action: <strong>${action}</strong>?`,
//                                 () => {
//                                     frappe.call({
//                                         method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.handle_dynamic_workflow_action",
//                                         args: {
//                                             doctype: frm.doc.doctype,
//                                             docname: frm.doc.name,
//                                             action: action
//                                         },
//                                         callback: function(res) {
//                                             frappe.msgprint(`✅ Workflow updated to: ${res.message}`);
//                                             frm.reload_doc();
//                                         }
//                                     });
//                                 }
//                             );
//                         }, "Workflow Actions");
//                     });
//                 }
//             }
//         });
//     }
// });

// // frappe.listview_settings['Project Registration'] = {
// //     get_indicator(doc) {
// //         if (doc.workflow_state === "Approved") {
// //             return [__("Approved"), "green", "workflow_state,=,Approved"];
// //         }
// //         else if (doc.workflow_state === "Rejected") {
// //             return [__("Rejected"), "red", "workflow_state,=,Rejected"];
// //         }
// //         else if (doc.workflow_state === "Pending HoD Approval") {
// //             return [__("Pending HoD"), "orange", "workflow_state,=,Pending HoD Approval"];
// //         }
// //         else if (doc.workflow_state === "Pending Staff Approval") {
// //             return [__("Pending Staff"), "blue", "workflow_state,=,Pending Staff Approval"];
// //         }
// //         else {
// //             return [__(doc.workflow_state || "Unknown"), "orange", `workflow_state,=,${doc.workflow_state}`];
// //         }
// //     }
// // };

// // new

// frappe.listview_settings['Project Registration'] = {
//     add_fields: ["workflow_state"],
//     get_indicator(doc) {
//         if (doc.workflow_state === "Approved") {
//             return [__("Approved"), "green", "workflow_state,=,Approved"];
//         }
//         else if (doc.workflow_state === "Rejected") {
//             return [__("Rejected"), "red", "workflow_state,=,Rejected"];
//         }
//         else if (doc.workflow_state === "Pending HoD Approval") {
//             return [__("Pending HoD"), "orange", "workflow_state,=,Pending HoD Approval"];
//         }
//         else if (doc.workflow_state === "Pending Staff Approval") {
//             return [__("Pending Staff"), "blue", "workflow_state,=,Pending Staff Approval"];
//         }
//         else if (!doc.workflow_state) {
//             return [__("Not Started"), "gray", "workflow_state,is,empty"];
//         }
//         else {
//             return [__(doc.workflow_state || "Unknown"), "orange", `workflow_state,=,${doc.workflow_state}`];
//         }
//     }
// };

// // New Version Code

// // ─────────────────────────────────────────────
// // Client Script for Project Registration
// // Handles: Custom Workflow Buttons + Form Indicator + Onload Logging
// // ─────────────────────────────────────────────

// frappe.ui.form.on('Project Registration', {
//     // ✅ When form loads
//     onload: function(frm) {
//         if (!frm.is_new()) {
//             // Optional: log available workflow actions (server-side logging/debug)
//             frappe.call({
//                 method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.log_available_workflow_actions",
//                 args: {
//                     docname: frm.doc.name
//                 }
//             });
//         }
//     },

//     // ✅ When form is refreshed (after save, reload, etc.)
//     refresh: function(frm) {
//         // 🔹 Hide default workflow buttons
//         frm.page.clear_actions();
//         frm.clear_custom_buttons();

//         // 🔹 Don't run if new document (no workflow actions yet)
//         if (frm.is_new()) return;

//         // ✅ Show a colored indicator for current workflow state
//         if (frm.doc.workflow_state) {
//             frm.dashboard.add_indicator(
//                 frm.doc.workflow_state,
//                 get_color(frm.doc.workflow_state)
//             );
//         }

//         // ✅ Load available workflow actions dynamically from backend
//         frappe.call({
//             method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_available_workflow_actions",
//             args: {
//                 docname: frm.doc.name
//             },
//             callback: function(r) {
//                 const actions = r.message || [];

//                 if (actions.length > 0) {
//                     actions.forEach(action => {
//                         frm.add_custom_button(action, function () {
//                             frappe.confirm(
//                                 `Are you sure you want to perform action: <strong>${action}</strong>?`,
//                                 () => {
//                                     frappe.call({
//                                         method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.handle_dynamic_workflow_action",
//                                         args: {
//                                             doctype: frm.doc.doctype,
//                                             docname: frm.doc.name,
//                                             action: action
//                                         },
//                                         callback: function(res) {
//                                             frappe.msgprint(`✅ Workflow updated to: ${res.message}`);
//                                             frm.reload_doc();
//                                         }
//                                     });
//                                 }
//                             );
//                         }, "Workflow Actions");
//                     });
//                 }
//             }
//         });
//     }
// });

// // ✅ Helper function: Determine color for workflow state badge
// function get_color(workflow_state) {
//     switch (workflow_state) {
//         case "Approved": return "green";
//         case "Rejected": return "red";
//         case "Pending HoD Approval": return "orange";
//         case "Pending Staff Approval": return "blue";
//         default: return "gray";
//     }
// }

// // ─────────────────────────────────────────────
// // List View Settings: Project Registration
// // Controls the indicator color in list view
// // ─────────────────────────────────────────────

// frappe.listview_settings['Project Registration'] = {
//     add_fields: ["workflow_state"],

//     get_indicator(doc) {
//         if (doc.workflow_state === "Approved") {
//             return [__("Approved"), "green", "workflow_state,=,Approved"];
//         } else if (doc.workflow_state === "Rejected") {
//             return [__("Rejected"), "red", "workflow_state,=,Rejected"];
//         } else if (doc.workflow_state === "Pending HoD Approval") {
//             return [__("Pending HoD"), "orange", "workflow_state,=,Pending HoD Approval"];
//         } else if (doc.workflow_state === "Pending Staff Approval") {
//             return [__("Pending Staff"), "blue", "workflow_state,=,Pending Staff Approval"];
//         } else if (!doc.workflow_state) {
//             return [__("Not Started"), "gray", "workflow_state,is,empty"];
//         } else {
//             return [__(doc.workflow_state || "Unknown"), "orange", `workflow_state,=,${doc.workflow_state}`];
//         }
//     }
// };

// frappe.ui.form.on('Project Registration', {
//     refresh: function(frm) {
//         // Your existing code...

//         // Add these lines to log user info to browser console
//         console.log("frappe.user:", frappe.user);
//         console.log("User roles:", frappe.user_roles);

//         // Rest of your code...
//     }
// });

// v3

// // ─────────────────────────────────────────────
// // Client Script for Project Registration
// // Handles: Custom Workflow Buttons + Form Indicator + Onload Logging
// // ─────────────────────────────────────────────

// frappe.ui.form.on('Project Registration', {
//     /**
//      * Triggered when the form loads for the first time.
//      * Runs only once per document open.
//      */
//     onload: function(frm) {
//         // Only proceed if this is an existing document (not new)
//         if (!frm.is_new()) {
//             // Optionally log available workflow actions on server-side for debugging
//             frappe.call({
//                 method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.log_available_workflow_actions",
//                 args: { docname: frm.doc.name }
//             });

//             // Show the workflow state indicator on form load immediately
//             show_workflow_indicator(frm);
//         }
//     },

//     /**
//      * Triggered every time the form refreshes (save, reload, or open).
//      */
//     refresh: function(frm) {
//         // Clear default workflow buttons to avoid duplicates
//         frm.page.clear_actions();
//         frm.clear_custom_buttons();

//         // Skip if the document is new and has no workflow state
//         if (frm.is_new()) return;

//         // Show workflow state indicator (refresh indicator if state changed)
//         show_workflow_indicator(frm);

//         // Load available workflow actions dynamically from backend
//         frappe.call({
//             method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_available_workflow_actions",
//             args: { docname: frm.doc.name },
//             callback: function(r) {
//                 const actions = r.message || [];

//                 if (actions.length > 0) {
//                     actions.forEach(action => {
//                         // Add each workflow action as a custom button under "Workflow Actions"
//                         frm.add_custom_button(action, function () {
//                             // Ask for confirmation before running the action
//                             frappe.confirm(
//                                 `Are you sure you want to perform action: <strong>${action}</strong>?`,
//                                 () => {
//                                     // Call backend method to perform the workflow action
//                                     frappe.call({
//                                         method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.handle_dynamic_workflow_action",
//                                         args: {
//                                             doctype: frm.doc.doctype,
//                                             docname: frm.doc.name,
//                                             action: action
//                                         },
//                                         callback: function(res) {
//                                             frappe.msgprint(`✅ Workflow updated to: ${res.message}`);
//                                             // Reload the document to reflect the updated state
//                                             frm.reload_doc();
//                                         }
//                                     });
//                                 }
//                             );
//                         }, "Workflow Actions");
//                     });
//                 }
//             }
//         });

//         // Log current user info & roles in browser console for debugging
//         console.log("frappe.user:", frappe.user);
//         console.log("User roles:", frappe.user_roles);
//     }
// });

// /**
//  * Helper function to display a colored workflow state indicator badge in the form header.
//  * Called on both 'onload' and 'refresh' events.
//  *
//  * @param {object} frm - The current form object
//  */
// function show_workflow_indicator(frm) {
//     // Clear any existing indicator headline to avoid duplicates
//     frm.dashboard.clear_headline();

//     if (frm.doc.workflow_state) {
//         // Add an indicator badge with text and color depending on the workflow state
//         frm.dashboard.add_indicator(
//             frm.doc.workflow_state,
//             get_color(frm.doc.workflow_state)
//         );
//     } else {
//         // Show a default indicator for documents with no workflow state (likely Draft)
//         frm.dashboard.add_indicator(
//             "Draft",
//             "gray"
//         );
//     }
// }

// /**
//  * Returns a color string based on the current workflow state for consistent UI experience.
//  *
//  * @param {string} workflow_state - The current workflow state string
//  * @returns {string} - Color name to use for indicator
//  */
// function get_color(workflow_state) {
//     switch (workflow_state) {
//         case "Approved": return "green";
//         case "Rejected": return "red";
//         case "Pending Head Approval": return "orange";
//         case "Pending Staff Approval": return "blue";
//         case "Draft": return "gray";
//         default: return "gray";  // Fallback color for unknown states
//     }
// }

// // ─────────────────────────────────────────────
// // List View Settings: Project Registration
// // Controls the color indicator in list views based on workflow_state
// // ─────────────────────────────────────────────

// frappe.listview_settings['Project Registration'] = {
//     add_fields: ["workflow_state"],

//     get_indicator(doc) {
//         if (doc.workflow_state === "Approved") {
//             return [__("Approved"), "green", "workflow_state,=,Approved"];
//         } else if (doc.workflow_state === "Rejected") {
//             return [__("Rejected"), "red", "workflow_state,=,Rejected"];
//         } else if (doc.workflow_state === "Pending Head Approval") {
//             return [__("Pending Head Approval"), "orange", "workflow_state,=,Pending Head Approval"];
//         } else if (doc.workflow_state === "Pending Staff Approval") {
//             return [__("Pending Staff"), "blue", "workflow_state,=,Pending Staff Approval"];
//         } else if (!doc.workflow_state) {
//             return [__("Draft"), "gray", "workflow_state,is,empty"];
//         } else {
//             return [__(doc.workflow_state || "Unknown"), "gray", `workflow_state,=,${doc.workflow_state}`];
//         }
//     }
// };

// // v4
// ─────────────────────────────────────────────
// Client Script for Project Registration
// Handles: Custom Workflow Buttons + Form Indicator + Onload Logging
// ─────────────────────────────────────────────
// working
// frappe.ui.form.on("Project Registration", {
//     /**
//      * Triggered when the form loads for the first time.
//      * Runs only once per document open.
//      */
//     onload: function (frm) {
//         // Only proceed if this is an existing document (not new)
//         if (!frm.is_new()) {
//             // Optionally log available workflow actions on server-side for debugging
//             frappe.call({
//                 method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.log_available_workflow_actions",
//                 args: { docname: frm.doc.name },
//             });

//             // Show the workflow state indicator on form load immediately
//             show_workflow_indicator(frm);
//         }
//     },

//     /**
//      * Triggered every time the form refreshes (save, reload, or open).
//      */
//     refresh: function (frm) {
//         // Clear default workflow buttons to avoid duplicates
//         frm.page.clear_actions();
//         frm.clear_custom_buttons();

//         // Skip if the document is new and has no workflow state
//         if (frm.is_new()) return;

//         // Show workflow state indicator (refresh indicator if state changed)
//         show_workflow_indicator(frm);

//         // Load available workflow actions dynamically from backend
//         frappe.call({
//             method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_available_workflow_actions",
//             args: { docname: frm.doc.name },
//             callback: function (r) {
//                 const actions = r.message || [];
//                 console.log("frappe.actions:", frm.doc.name);
//                 if (actions.length > 0) {
//                     actions.forEach((action) => {
//                         console.log("frappe.action:", action);
//                         // Add each workflow action as a custom button under "Workflow Actions"
//                         frm.add_custom_button(
//                             action,
//                             function () {
//                                 // Ask for confirmation before running the action
//                                 frappe.confirm(
//                                     `Are you sure you want to perform action: <strong>${action}</strong>?`,
//                                     () => {
//                                         // Call backend method to perform the workflow action
//                                         frappe.call({
//                                             method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.handle_dynamic_workflow_action",
//                                             args: {
//                                                 doctype: frm.doc.doctype,
//                                                 docname: frm.doc.name,
//                                                 action: action,
//                                             },
//                                             callback: function (res) {
//                                                 frappe.msgprint(
//                                                     `✅ Workflow updated to: ${res.message}`,
//                                                 );
//                                                 // Reload the document to reflect the updated state
//                                                 frm.reload_doc();
//                                             },
//                                         });
//                                     },
//                                 );
//                             },
//                             "Workflow Actions",
//                         );
//                     });
//                 }
//             },
//         });

//         // Log current user info & roles in browser console for debugging
//         console.log("frappe.user:", frappe.user);
//         console.log("User roles:", frappe.user_roles);
//         console.log("User frm:", frm.doc.name);
//     },
// });

// jimmy v5

// frappe.ui.form.on("Project Registration", {
//     onload: function (frm) {
//         // Run only for existing documents
//         if (!frm.is_new()) {
//             frappe.call({
//                 method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.log_available_workflow_actions",
//                 args: { docname: frm.doc.name },
//                 callback: function (r) {
//                     console.log("Available actions (onload):", r.message);
//                 },
//             });
//             show_workflow_indicator(frm);
//         }
//     },

//     refresh: function (frm) {
//         // Clear default workflow buttons to prevent duplicates
//         frm.page.clear_actions();
//         frm.clear_custom_buttons();

//         // Skip new documents (no workflow state yet)
//         if (frm.is_new()) return;

//         // Always show the current workflow indicator
//         show_workflow_indicator(frm);

//         // Fetch workflow actions AFTER the form has fully loaded
//         frappe.after_ajax(() => {
//             frappe.call({
//                 method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_available_workflow_actions",
//                 args: { docname: frm.doc.name },
//                 callback: function (r) {
//                     const actions = r.message || [];

//                     if (!Array.isArray(actions) || actions.length === 0) {
//                         console.log(
//                             "⚠️ No available workflow actions for this user/state.",
//                         );
//                         return;
//                     }

//                     // Add workflow buttons under a common group
//                     actions.forEach((action) => {
//                         frm.add_custom_button(
//                             action,
//                             function () {
//                                 frappe.confirm(
//                                     `Are you sure you want to perform action: <strong>${action}</strong>?`,
//                                     () => {
//                                         frappe.call({
//                                             method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.handle_dynamic_workflow_action",
//                                             args: {
//                                                 doctype: frm.doc.doctype,
//                                                 docname: frm.doc.name,
//                                                 action: action,
//                                             },
//                                             callback: function (res) {
//                                                 if (res.message) {
//                                                     frappe.msgprint(
//                                                         `✅ Workflow updated to: ${res.message}`,
//                                                     );
//                                                     frm.reload_doc();
//                                                 } else {
//                                                     frappe.msgprint(
//                                                         `❌ No response from server for action: ${action}`,
//                                                     );
//                                                 }
//                                             },
//                                             error: function (err) {
//                                                 console.error(
//                                                     "Workflow action error:",
//                                                     err,
//                                                 );
//                                                 frappe.msgprint(
//                                                     "⚠️ Failed to perform the workflow action. Check console logs.",
//                                                 );
//                                             },
//                                         });
//                                     },
//                                 );
//                             },
//                             __("Workflow Actions"), // Localized label
//                         );
//                     });

//                     // Show action menu
//                     frm.page.set_inner_btn_group_as_primary(
//                         __("Workflow Actions"),
//                     );
//                 },
//                 error: function (err) {
//                     console.error("Error fetching workflow actions:", err);
//                     frappe.msgprint(
//                         "⚠️ Could not fetch workflow actions. Check console for details.",
//                     );
//                 },
//             });
//         });

//         // Log user data for debugging
//         console.log("Docstatus:", frm.doc.docstatus);
//         console.log("Current user:", frappe.session.user);
//         console.log("Owner:", frm.doc.owner);
//         console.log("User roles:", frappe.user_roles);

//     },
// });

// New v7

frappe.ui.form.on("Project Registration", {
    /**
     * Triggered when the form loads for the first time.
     * Runs only once per document open.
     */
    onload: function (frm) {
        // Only proceed if this is an existing document (not new)
        if (!frm.is_new()) {
            // Optionally log available workflow actions on server-side for debugging
            frappe.call({
                method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.log_available_workflow_actions",
                args: { docname: frm.doc.name },
            });

            // Show the workflow state indicator on form load immediately
            show_workflow_indicator(frm);

            // Handle Endorsement visibility logic unconditionally on load
            if (frm.doc.workflow_state === "Endorsement Draft" || frm.doc.workflow_state === "Pending Dean Approval") {
                frm.set_df_property("signature_of_the_head_of_institute", "hidden", 1);
            }
        }
    },

    /**
     * Triggered every time the form refreshes (save, reload, or open).
     */
    refresh: function (frm) {
        // Clear default workflow buttons to avoid duplicates
        frm.page.clear_actions();
        frm.clear_custom_buttons();

        // Skip if the document is new and has no workflow state
        if (frm.is_new()) return;

        // Show workflow state indicator (refresh indicator if state changed)
        show_workflow_indicator(frm);

        // Handle Endorsement visibility logic
        if (frm.doc.workflow_state === "Endorsement Draft" || frm.doc.workflow_state === "Pending Dean Approval") {
            frm.set_df_property("signature_of_the_head_of_institute", "hidden", 1);

            // If it's pending approval, lock the form for non-approvers
            if (frm.doc.workflow_state === "Pending Dean Approval") {
                if (!frappe.user_roles.includes("System Manager") && frappe.session.user !== "dornd@iitg.ac.in" && !frappe.user_roles.includes("All_ProRnd_User")) {
                    frm.disable_form();
                }
            }
        } else {
            frm.set_df_property("signature_of_the_head_of_institute", "hidden", 0);

            if (frm.doc.workflow_state === "Endorsement Approved" && frm.doc.owner === frappe.session.user) {
                frm.enable_form();
            }
        }

        // Load available workflow actions dynamically from backend
        frappe.call({
            method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_available_workflow_actions",
            args: { docname: frm.doc.name },
            callback: function (r) {
                const actions = r.message || [];
                console.log("frappe.actions:", frm.doc.name);
                if (actions.length > 0) {
                    actions.forEach((action) => {
                        console.log("frappe.action:", action);

                        // --- Filter for HOD button ---
                        if (
                            frm.doc.workflow_state === "Pending Head Approval"
                        ) {
                            // If current user is NOT the head_approver, skip showing the button
                            if (frm.doc.head_approver !== frappe.session.user) {
                                console.log(
                                    `Skipping HOD button for user ${frappe.session.user}`,
                                );
                                return;
                            }
                        }

                        // Add each workflow action as a custom button under "Workflow Actions"
                        frm.add_custom_button(
                            action,
                            function () {
                                // Ask for confirmation before running the action
                                frappe.confirm(
                                    `Are you sure you want to perform action: <strong>${action}</strong>?`,
                                    () => {
                                        // Call backend method to perform the workflow action
                                        frappe.call({
                                            method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.handle_dynamic_workflow_action",
                                            args: {
                                                doctype: frm.doc.doctype,
                                                docname: frm.doc.name,
                                                action: action,
                                            },
                                            callback: function (res) {
                                                frappe.msgprint(
                                                    `✅ Workflow updated to: ${res.message}`,
                                                );
                                                // Reload the document to reflect the updated state
                                                frm.reload_doc();
                                            },
                                        });
                                    },
                                );
                            },
                            "Workflow Actions",
                        );
                    });
                }
            },
        });

        // Log current user info & roles in browser console for debugging
        console.log("frappe.user:", frappe.user);
        console.log("User roles:", frappe.user_roles);
        console.log("User frm:", frm.doc.name);
    },
});

/**
 * Helper function to display a colored workflow state indicator badge in the form header.
 * Called on both 'onload' and 'refresh' events.
 *
 * @param {object} frm - The current form object
 */
function show_workflow_indicator(frm) {
    // Clear any existing indicator headline to avoid duplicates
    frm.dashboard.clear_headline();

    if (frm.doc.workflow_state) {
        // Add an indicator badge with text and color depending on the workflow state
        frm.dashboard.add_indicator(
            frm.doc.workflow_state,
            get_color(frm.doc.workflow_state),
        );
    } else {
        // Show a default indicator for documents with no workflow state (likely Draft)
        frm.dashboard.add_indicator("Draft", "gray");
    }
}

/**
 * Returns a color string based on the current workflow state for consistent UI experience.
 *
 * @param {string} workflow_state - The current workflow state string
 * @returns {string} - Color name to use for indicator
 */
function get_color(workflow_state) {
    switch (workflow_state) {
        case "Approved":
            return "green";
        case "Endorsement Approved":
            return "green";
        case "Rejected":
            return "red";
        case "Pending HoD Approval":
        case "Pending Dean Approval":
            return "orange";
        case "Pending Staff Approval":
            return "blue";
        case "Endorsement Draft":
        case "Draft":
            return "gray";
        default:
            return "gray"; // Fallback color for unknown states
    }
}

// ─────────────────────────────────────────────
// List View Settings: Project Registration
// Controls the color indicator in list views based on workflow_state
// ─────────────────────────────────────────────

frappe.listview_settings["Project Registration"] = {
    add_fields: ["workflow_state"],

    get_indicator(doc) {
        if (doc.workflow_state === "Approved") {
            return [__("Approved"), "green", "workflow_state,=,Approved"];
        } else if (doc.workflow_state === "Rejected") {
            return [__("Rejected"), "red", "workflow_state,=,Rejected"];
        } else if (doc.workflow_state === "Pending Head Approval") {
            return [
                __("Pending Head Approval"),
                "orange",
                "workflow_state,=,Pending Head Approval",
            ];
        } else if (doc.workflow_state === "Pending Staff Approval") {
            return [
                __("Pending Staff"),
                "blue",
                "workflow_state,=,Pending Staff Approval",
            ];
        } else if (doc.workflow_state === "Endorsement Approved") {
            return [__("Endorsement Approved"), "green", "workflow_state,=,Endorsement Approved"];
        } else if (doc.workflow_state === "Pending Dean Approval") {
            return [
                __("Pending Dean"),
                "purple",
                "workflow_state,=,Pending Dean Approval",
            ];
        } else if (doc.workflow_state === "Endorsement Draft") {
            return [__("Endorsement Draft"), "gray", "workflow_state,=,Endorsement Draft"];
        } else if (!doc.workflow_state) {
            return [__("Draft"), "gray", "workflow_state,is,empty"];
        } else {
            return [
                __(doc.workflow_state || "Unknown"),
                "orange",
                `workflow_state,=,${doc.workflow_state}`,
            ];
        }
    },
};

// // v5

// // ─────────────────────────────────────────────
// // Client Script for Project Registration
// // Handles: Custom Workflow Buttons + Form Indicator + Robust onload indicator fix
// // ─────────────────────────────────────────────

// frappe.ui.form.on('Project Registration', {
//     /**
//      * Triggered when the form loads for the first time.
//      * Runs only once per document open.
//      * We do NOT add indicators or buttons here because the form elements might not be ready.
//      * Instead, we rely on the 'refresh' event to handle all UI rendering reliably.
//      */
//     onload: function(frm) {
//         if (!frm.is_new()) {
//             // Optional: You can perform non-UI backend calls here if needed.
//             // For example, pre-loading some data.
//             console.log("Form loaded. UI elements will be set up in refresh event.");
//         }
//     },

//     /**
//      * Triggered every time the form refreshes (e.g., on open, save, or reload).
//      * This is the recommended event for safely adding custom UI elements like buttons and indicators.
//      */
//     refresh: function(frm) {
//         // 1. Clear previous custom elements to prevent duplicates on refresh.
//         frm.page.clear_actions();
//         frm.clear_custom_buttons();

//         // Don't proceed for new, unsaved documents.
//         if (frm.is_new()) {
//             return;
//         }

//         // 2. Set up the dashboard indicator robustly.
//         setup_dashboard_indicator(frm);

//         // 3. Load and display dynamic workflow action buttons.
//         setup_workflow_buttons(frm);

//         // Debug logs
//         console.log("Current user:", frappe.user);
//         console.log("User roles:", frappe.user_roles);
//     }
// });

// /**
//  * Safely adds the workflow state indicator to the form's dashboard.
//  * It checks if the dashboard is ready and uses a short delay as a fallback.
//  *
//  * @param {object} frm - The current form object.
//  */
// function setup_dashboard_indicator(frm) {
//     // This is the function that will perform the actual indicator addition.
//     const add_indicator = () => {
//         // FIX: Use `frm.dashboard.indicator_area.empty()` to clear ONLY the indicators.
//         // `clear_headline()` incorrectly removes the document title.
//         if (frm.dashboard && frm.dashboard.indicator_area) {
//             frm.dashboard.indicator_area.empty();
//         }

//         const state = frm.doc.workflow_state || "Draft";
//         const color = get_indicator_color(state);
//         frm.dashboard.add_indicator(state, color);
//     };

//     // Check if the dashboard is ready immediately.
//     if (frm.dashboard) {
//         add_indicator();
//     } else {
//         // If not ready, wait a very short moment for it to initialize.
//         // This is a more robust, non-recursive fallback.
//         setTimeout(() => {
//             if (frm.dashboard) {
//                 add_indicator();
//             } else {
//                 console.error("Dashboard failed to initialize in time.");
//             }
//         }, 150); // A 150ms delay is usually enough for async rendering.
//     }
// }

// /**
//  * Fetches available workflow actions from the backend and adds them as custom buttons.
//  *
//  * @param {object} frm - The current form object.
//  */
// function setup_workflow_buttons(frm) {
//     frappe.call({
//         method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_available_workflow_actions",
//         args: { docname: frm.doc.name },
//         callback: function(r) {
//             const actions = r.message || [];

//             if (actions.length > 0) {
//                 actions.forEach(action => {
//                     frm.add_custom_button(action, function () {
//                         frappe.confirm(
//                             `Are you sure you want to perform the action: <strong>${action}</strong>?`,
//                             () => { // This is the 'yes' callback for the confirmation
//                                 frappe.call({
//                                     method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.handle_dynamic_workflow_action",
//                                     args: {
//                                         doctype: frm.doc.doctype,
//                                         docname: frm.doc.name,
//                                         action: action
//                                     },
//                                     callback: function(res) {
//                                         if (res.message) {
//                                             frappe.msgprint({
//                                                 title: __('Success'),
//                                                 message: `✅ Workflow updated to: ${res.message}`,
//                                                 indicator: 'green'
//                                             });
//                                             frm.reload_doc();
//                                         }
//                                     }
//                                 });
//                             }
//                         );
//                     }, "Workflow Actions"); // Group buttons under a dropdown menu.
//                 });
//             }
//         }
//     });
// }

// /**
//  * Returns a color string based on the workflow state.
//  * Renamed to be more specific (distinguishing from list view's get_indicator).
//  *
//  * @param {string} workflow_state
//  * @returns {string} color
//  */
// function get_indicator_color(workflow_state) {
//     const color_map = {
//         "Approved": "green",
//         "Rejected": "red",
//         "Pending Head Approval": "orange",
//         "Pending Staff Approval": "blue",
//         "Draft": "gray"
//     };
//     return color_map[workflow_state] || "gray";
// }

// // ─────────────────────────────────────────────
// // List View Settings for Project Registration
// // DEBUGGING VERSION - WITH ERROR HANDLING
// // ─────────────────────────────────────────────

// frappe.listview_settings['Project Registration'] = {

//     refresh: function(listview) {
//         console.log("Listview onload triggered. Preparing to fetch workflow states.");

//         const doc_names = listview.data.map(doc => doc.name);

//         if (doc_names.length === 0) {
//             console.log("No documents in list view, skipping API call.");
//             return;
//         }

//         console.log("Found documents:", doc_names);
//         console.log("Initiating frappe.call to get_workflow_states_for_docs...");

//         frappe.call({
//             method: "rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_workflow_states_for_docs",
//             args: {
//                 doc_names: doc_names
//             },
//             // This runs ONLY on a successful call
//             callback: function(response) {
//                 console.log("SUCCESS: API call returned a response.");
//                 const states_data = response.message;
//                 if (!states_data || states_data.length === 0) {
//                     console.error("API call was successful but returned no data.");
//                     return;
//                 }

//                 console.log("states_data:", states_data); // Your original log

//                 const state_map = new Map(states_data.map(d => [d.name, d.workflow_state]));

//                 state_map.forEach((state, name) => {
//                     const row = $(`.list-row-container[data-name='${name}']`);
//                     const indicator = row.find('.indicator');

//                     if (indicator.length > 0) {
//                         const color = get_indicator_color(state);
//                         const state_text = state || "Submitted";
//                         indicator.removeClass('red green blue orange gray darkgrey').addClass(color).text(state_text);
//                     }
//                 });
//             },
//             // THIS IS THE CRITICAL PART - It runs ONLY on a failed call
//             error: function(r) {
//                 console.error("ERROR: The API call failed!");
//                 console.error("Server Response:", r);
//                 frappe.msgprint({
//                     title: __('API Call Failed'),
//                     indicator: 'red',
//                     message: __("Could not fetch workflow states. See the browser's developer console for details.")
//                 });
//             }
//         });
//     }
// };

// /**
//  * A helper function to map a workflow state to a color class.
//  */
// function get_indicator_color(state) {
//     const color_map = {
//         "Approved": "green",
//         "Rejected": "red",
//         "Pending Head Approval": "orange",
//         "Pending Staff Approval": "blue",
//         "Draft": "gray"
//     };
//     return color_map[state] || "darkgrey";
// }
