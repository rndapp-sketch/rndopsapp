"""
Workflow Module for Project Registration
Handles workflow state transitions, role-based access control, and action validation.
"""

import frappe


class ProjectWorkflow:
    """Manages workflow operations for Project Registration documents."""
    
    DOCTYPE = "Project Registration"
    
    def __init__(self, docname):
        """Initialize workflow with document."""
        self.doc = frappe.get_doc(self.DOCTYPE, docname)
        self.docname = docname
        self.current_state = self.doc.workflow_state or "Draft"
        self.user_roles = frappe.get_roles(frappe.session.user)
        self.workflow = self._get_workflow()
    
    def _get_workflow(self):
        """Fetch workflow document for this doctype."""
        workflow_name = frappe.get_value(
            "Workflow",
            {"document_type": self.doc.doctype},
            "name"
        )
        if not workflow_name:
            return None
        return frappe.get_doc("Workflow", workflow_name)
    
    def _is_system_manager(self):
        """Check if user is System Manager."""
        return "System Manager" in self.user_roles
    
    def _get_state_allowed_roles(self):
        """Get roles allowed to act on current state."""
        if not self.workflow:
            return []
        
        allowed_roles = []
        for state in self.workflow.states:
            if state.state == self.current_state:
                if isinstance(state.allow_edit, list):
                    allowed_roles.extend(state.allow_edit)
                elif state.allow_edit:
                    allowed_roles.append(state.allow_edit)
                break
        return allowed_roles
    
    def _can_user_act(self):
        """Check if current user can perform workflow actions."""
        if self._is_system_manager():
            return True
        
        allowed_roles = self._get_state_allowed_roles()
        return any(role in self.user_roles for role in allowed_roles)
    
    def _get_transition_roles(self, transition):
        """Extract allowed roles from transition."""
        transition_roles = transition.get("allowed") or []
        if isinstance(transition_roles, str):
            transition_roles = [transition_roles]
        return transition_roles
    
    def get_available_actions(self):
        """
        Get list of available workflow actions for current user.
        Returns list of action names user can perform from current state.
        """
        if not self.workflow:
            return []
        
        allowed_actions = []
        
        for transition in self.workflow.get("transitions", []):
            # Check if transition is from current state
            if transition.state != self.current_state:
                continue
            
            # Check role permissions on transition
            transition_roles = self._get_transition_roles(transition)
            
            # User can perform action if they have allowed role or are System Manager
            if self._is_system_manager() or any(role in self.user_roles for role in transition_roles):
                allowed_actions.append(transition.action)
        
        # Remove duplicates while preserving order
        allowed_actions = list(dict.fromkeys(allowed_actions))
        return allowed_actions
    
    def get_valid_transitions(self):
        """
        Get all valid transitions from current state.
        Returns list of formatted transition strings.
        """
        if not self.workflow:
            return []
        
        valid_actions = []
        for transition in self.workflow.transitions:
            if transition.state == self.current_state:
                valid_actions.append(f"{transition.action} → {transition.next_state}")
        
        return valid_actions
    
    def get_next_state(self, action):
        """Find next state for given action from current state."""
        if not self.workflow:
            return None
        
        for transition in self.workflow.transitions:
            if transition.state == self.current_state and transition.action == action:
                return transition.next_state
        
        return None
    
    def perform_action(self, action):
        """
        Execute workflow action and update document state.
        
        Args:
            action (str): Action name to perform
            
        Returns:
            str: New workflow state
            
        Raises:
            frappe.PermissionError: If user cannot perform action
            frappe.ValidationError: If action is invalid
        """
        if not self.workflow:
            frappe.throw("Workflow not found.")
        
        # Check permissions
        if not self._can_user_act():
            frappe.throw("You do not have permission to perform workflow actions.")
        
        # Find next state
        next_state = self.get_next_state(action)
        if not next_state:
            frappe.throw(f"Invalid action '{action}' from state '{self.current_state}'.")
        
        # Update and save document
        if self.doc.docstatus != 2:  # not cancelled
            self.doc.workflow_state = next_state
            self.doc.save(ignore_permissions=True)
        
        return next_state
    
    def log_debug_info(self):
        """Log detailed workflow debug information for troubleshooting."""
        workflow_name = frappe.get_value(
            "Workflow",
            {"document_type": self.doc.doctype},
            "name"
        )
        
        frappe.msgprint(f"Workflow Name: <b>{workflow_name}</b>")
        frappe.msgprint(f"Current Workflow State: <b>{self.current_state}</b>")
        frappe.msgprint(f"Your roles: <b>{', '.join(self.user_roles)}</b>")
        
        if not self.workflow:
            frappe.msgprint("⚠ No workflow is configured.")
            return
        
        allowed_roles = self._get_state_allowed_roles()
        frappe.msgprint(f"Roles allowed at this state: <b>{', '.join(allowed_roles)}</b>")
        
        can_act = self._can_user_act()
        if not can_act:
            frappe.msgprint("🚫 You are not allowed to perform any workflow actions.")
            return
        
        valid_transitions = self.get_valid_transitions()
        if valid_transitions:
            frappe.msgprint("Available Workflow Actions:<br>" + "<br>".join(valid_transitions))
            frappe.msgprint(f"Document: <b>{self.docname}</b>")
        else:
            frappe.msgprint("⚠ No available workflow actions from current state.")


# Frappe API Endpoints

@frappe.whitelist()
def get_available_workflow_actions(docname):
    """
    Get list of workflow actions available to current user.
    
    Args:
        docname (str): Project Registration document name
        
    Returns:
        list: Action names user can perform
    """
    workflow = ProjectWorkflow(docname)
    actions = workflow.get_available_actions()
    frappe.logger().warning(f"Available actions for {docname}: {actions}")
    return actions


@frappe.whitelist()
def perform_workflow_action(docname, action):
    """
    Execute workflow action and transition document state.
    
    Args:
        docname (str): Project Registration document name
        action (str): Action name to perform
        
    Returns:
        str: New workflow state
    """
    workflow = ProjectWorkflow(docname)
    return workflow.perform_action(action)


@frappe.whitelist()
def get_workflow_actions(docname):
    """
    Get workflow actions with detailed transition information.
    
    Args:
        docname (str): Project Registration document name
        
    Returns:
        dict: Message containing available transitions or error message
    """
    workflow = ProjectWorkflow(docname)
    
    if not workflow.workflow:
        return {"message": ["No workflow configured."]}
    
    if not workflow._can_user_act():
        return {"message": ["🚫 You are not allowed to perform any workflow actions."]}
    
    valid_actions = workflow.get_valid_transitions()
    if not valid_actions:
        return {"message": ["⚠ No available workflow actions from current state."]}
    
    return {"message": valid_actions}


@frappe.whitelist()
def log_available_workflow_actions(docname):
    """
    Log detailed workflow information for debugging.
    
    Args:
        docname (str): Project Registration document name
    """
    workflow = ProjectWorkflow(docname)
    workflow.log_debug_info()