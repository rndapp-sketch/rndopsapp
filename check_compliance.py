
import os
import json
import re

DOCTYPE_DIR = "/home/prornd/project/frappe_dev/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype"

def check_compliance():
    compliance_report = []
    
    for folder in os.listdir(DOCTYPE_DIR):
        folder_path = os.path.join(DOCTYPE_DIR, folder)
        if not os.path.isdir(folder_path) or folder.startswith('__'):
            continue
            
        json_file = os.path.join(folder_path, f"{folder}.json")
        py_file = os.path.join(folder_path, f"{folder}.py")
        
        if not os.path.exists(json_file):
            continue
            
        with open(json_file, 'r') as f:
            try:
                doctype_meta = json.load(f)
            except:
                continue
                
        # Skip Child Tables and typically singular configs if they don't look like main forms
        if doctype_meta.get("istable"):
            continue

        # Skip Single doctypes if they are just settings (heuristic)
        # if doctype_meta.get("issingle"):
        #     pass 

        if not os.path.exists(py_file):
             compliance_report.append({"doctype": folder, "status": "Missing .py file"})
             continue
             
        with open(py_file, 'r') as f:
            content = f.read()
            
        has_get_fields = re.search(r'def\s+get_.*_fields', content)
        has_save_data = re.search(r'def\s+save_.*', content)
        
        missing = []
        if not has_get_fields:
            missing.append("get_fields")
        if not has_save_data:
            missing.append("save_data")
            
        if missing:
             compliance_report.append({
                 "doctype": folder,
                 "status": "Incomplete",
                 "missing": missing
             })
        else:
            # compliance_report.append({"doctype": folder, "status": "Compliant"})
            pass

    print(json.dumps(compliance_report, indent=2))

if __name__ == "__main__":
    check_compliance()
