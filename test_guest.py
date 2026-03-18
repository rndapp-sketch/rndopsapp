import frappe

def test():
    frappe.set_user("Guest")
    try:
        docs = frappe.get_all("Recruitment Adhoc Contractual", filters={"webmail_id": "ls@iitg.ac.in"}, pluck="name")
        print("Guest can read get_all:", docs)
        if docs:
            doc = frappe.get_doc("Recruitment Adhoc Contractual", docs[0])
            print("Guest can read get_doc:", doc.name)
    except Exception as e:
        print("Exception:", str(e))

