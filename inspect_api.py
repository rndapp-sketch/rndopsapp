
import sys
import os

# Set up path to find frappe
# Assuming we are in /home/prornd/project/frappe_dev/prornd/apps/rndopsapp
# Bench root is ../../
BENCH_ROOT = os.path.abspath(os.path.join(os.getcwd(), "../../"))
sys.path.append(os.path.join(BENCH_ROOT, "apps", "frappe"))
sys.path.append(os.path.join(BENCH_ROOT, "apps", "rndopsapp"))

try:
    import frappe
except ImportError:
    # Fallback if frappe is installed in env site-packages
    pass

import inspect
import pkgutil
import importlib

def get_whitelisted_methods():
    app_name = "rndopsapp"
    methods = []
    
    print(f"Scanning app: {app_name}")

    # 1. Inspect api.py
    try:
        api_module = importlib.import_module(f"{app_name}.{app_name}.api")
        print(f"Successfully imported {app_name}.api")
        for name, func in inspect.getmembers(api_module, inspect.isfunction):
            if hasattr(func, "whitelist") and func.whitelist:
                print(f"Found api method: {name}")
                methods.append({
                    "module": "api",
                    "name": name,
                    "doc": func.__doc__
                })
    except ImportError as e:
        print(f"Could not import api.py: {e}")
    except Exception as e:
        print(f"Error inspecting api.py: {e}")

    # 2. Inspect DocTypes
    try:
        doctypes = frappe.get_all("DocType", filters={"module": "rndopsapp"}, fields=["name"])
        print(f"Found {len(doctypes)} DocTypes in rndopsapp")
        
        for dt in doctypes:
            try:
                # Construct module path: app.app.doctype.name.name
                # Note: module name in file system is usually scrubbed (snake_case)
                scrubbed_name = frappe.scrub(dt.name)
                module_path = f"{app_name}.{app_name}.doctype.{scrubbed_name}.{scrubbed_name}"
                
                module = importlib.import_module(module_path)
                
                for name, func in inspect.getmembers(module, inspect.isfunction):
                    if hasattr(func, "whitelist") and func.whitelist:
                        # print(f"Found method in {dt.name}: {name}")
                        methods.append({
                            "module": dt.name,
                            "name": name,
                            "doc": func.__doc__
                        })
            except ImportError:
                # Some DocTypes might not have a controller file or it's named differently
                # print(f"Skipping {dt.name} (no module found at {module_path})")
                pass
            except Exception as e:
                print(f"Error inspecting {dt.name}: {e}")
    except Exception as e:
        print(f"Error getting DocTypes: {e}")

    return methods

if __name__ == "__main__":
    # Initialize Frappe
    try:
        # Change to bench root to find sites
        os.chdir(BENCH_ROOT)
        frappe.init(site="prornd.local")
        frappe.connect()
        
        methods = get_whitelisted_methods()
        print(f"\nTotal whitelisted methods found: {len(methods)}")
        for m in methods:
            print(f"[{m['module']}] {m['name']}")
    except Exception as e:
        print(f"Initialization failed: {e}")
