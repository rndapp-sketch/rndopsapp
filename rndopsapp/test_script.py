import requests

url = "http://172.16.134.81:8000/api/method/rndopsapp.rndopsapp.doctype.disbursal_of_honorarium.disbursal_of_honorarium.save_disbursal_of_honorarium_data"
headers = {
    "Authorization": "token 8ct3r2h4hv:some_secret",  # Won't use since we are just checking if it crashes
    "Content-Type": "application/json"
}

# The bug report says this payload drops project details
payload = {
    "data": {
        "applying_for_self_or_other": "Self",
        "project_name": "2026022501MeiTy000555",
        "project_number": "26C0556BSBESP0391xxLS",
        "account_head": "Some Head",
        "approval_comp_authority": "Yes",
        "total_amount": 5000
    }
}

# Let's bypass auth by running this directly within frappe shell via bench? Wait, I can't use bench.
