"""
API Documentation Generator for rndopsapp
Generates OpenAPI 3.0 schema for all whitelisted methods
"""

import frappe
import inspect
import importlib
from typing import Dict, List, Any


@frappe.whitelist()
def get_api_schema():
	"""
	Returns OpenAPI 3.0 compliant schema for all whitelisted methods in rndopsapp.
	This endpoint is used by the API Docs page to render Swagger UI.
	"""
	app_name = "rndopsapp"
	
	# Build the OpenAPI schema
	schema = {
		"openapi": "3.0.0",
		"info": {
			"title": "RnDOps API Documentation",
			"description": "Auto-generated API documentation for all whitelisted endpoints in the rndopsapp module.",
			"version": "1.0.0"
		},
		"servers": [
			{
				"url": frappe.utils.get_url(),
				"description": "Current Frappe Site"
			}
		],
		"paths": {},
		"components": {
			"securitySchemes": {
				"ApiKeyAuth": {
					"type": "apiKey",
					"in": "header",
					"name": "Authorization",
					"description": "Use 'token <api_key>:<api_secret>' format"
				}
			}
		},
		"security": [{"ApiKeyAuth": []}]
	}
	
	# Discover all whitelisted methods
	methods = get_whitelisted_methods()
	
	# Convert to OpenAPI paths
	for method in methods:
		path = f"/api/method/{app_name}.{app_name}.{method['module_path']}.{method['name']}"
		
		# Parse docstring for description
		description = method.get('doc', '').strip() if method.get('doc') else f"Endpoint: {method['name']}"
		
		# Extract parameters from function signature
		parameters = []
		request_body = None
		
		if method.get('params'):
			# If we have parameters, create request body for POST
			properties = {}
			required = []
			
			for param in method['params']:
				param_name = param['name']
				properties[param_name] = {
					"type": "string",
					"description": f"Parameter: {param_name}"
				}
				if param.get('required', False):
					required.append(param_name)
			
			request_body = {
				"content": {
					"application/json": {
						"schema": {
							"type": "object",
							"properties": properties,
							"required": required if required else None
						}
					}
				}
			}
		
		# Create path item
		schema["paths"][path] = {
			"post": {
				"summary": method['name'],
				"description": description,
				"operationId": f"{method['module']}.{method['name']}",
				"tags": [method['module']],
				"requestBody": request_body,
				"responses": {
					"200": {
						"description": "Successful response",
						"content": {
							"application/json": {
								"schema": {
									"type": "object"
								}
							}
						}
					},
					"403": {
						"description": "Permission denied"
					},
					"500": {
						"description": "Server error"
					}
				}
			}
		}
	
	return schema


def get_whitelisted_methods() -> List[Dict[str, Any]]:
	"""
	Scans the rndopsapp module for all whitelisted methods.
	Returns a list of method metadata.
	"""
	app_name = "rndopsapp"
	methods = []
	
	# Get Frappe's global whitelisted list
	import frappe as frappe_module
	whitelisted_functions = getattr(frappe_module, 'whitelisted', [])
	
	frappe.log_error(f"Total whitelisted functions in Frappe: {len(whitelisted_functions)}", "API Docs Generator")
	
	# 1. Scan api.py
	try:
		api_module = importlib.import_module(f"{app_name}.{app_name}.api")
		for name, func in inspect.getmembers(api_module, inspect.isfunction):
			# Check if function is in the global whitelisted list
			if func in whitelisted_functions:
				params = extract_parameters(func)
				methods.append({
					"module": "api",
					"module_path": "api",
					"name": name,
					"doc": func.__doc__,
					"params": params
				})
				frappe.log_error(f"Found whitelisted method in api.py: {name}", "API Docs Generator")
	except ImportError as e:
		frappe.log_error(f"Could not import api.py: {str(e)}", "API Docs Generator")
	except Exception as e:
		frappe.log_error(str(e), "API Docs Generator - api.py")
	
	# 2. Scan DocTypes
	try:
		doctypes = frappe.get_all("DocType", filters={"module": "Rndopsapp"}, fields=["name"])
		frappe.log_error(f"Found {len(doctypes)} doctypes in Rndopsapp", "API Docs Generator")
		
		for dt in doctypes:
			try:
				scrubbed_name = frappe.scrub(dt.name)
				module_path = f"{app_name}.{app_name}.doctype.{scrubbed_name}.{scrubbed_name}"
				
				module = importlib.import_module(module_path)
				
				for name, func in inspect.getmembers(module, inspect.isfunction):
					# Check if function is in the global whitelisted list
					if func in whitelisted_functions:
						params = extract_parameters(func)
						methods.append({
							"module": dt.name,
							"module_path": f"doctype.{scrubbed_name}.{scrubbed_name}",
							"name": name,
							"doc": func.__doc__,
							"params": params
						})
						frappe.log_error(f"Found whitelisted method in {dt.name}: {name}", "API Docs Generator")
			except ImportError:
				# DocType has no controller
				pass
			except Exception as e:
				frappe.log_error(f"Error scanning {dt.name}: {str(e)}", "API Docs Generator")
	except Exception as e:
		frappe.log_error(str(e), "API Docs Generator - DocTypes")
	
	frappe.log_error(f"Total methods found: {len(methods)}", "API Docs Generator")
	return methods


def extract_parameters(func) -> List[Dict[str, Any]]:
	"""
	Extracts parameter information from a function signature.
	"""
	params = []
	try:
		sig = inspect.signature(func)
		for param_name, param in sig.parameters.items():
			# Skip 'self' and 'cls'
			if param_name in ['self', 'cls']:
				continue
			
			params.append({
				"name": param_name,
				"required": param.default == inspect.Parameter.empty,
				"default": None if param.default == inspect.Parameter.empty else param.default
			})
	except Exception:
		pass
	
	return params
