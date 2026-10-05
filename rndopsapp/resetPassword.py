import frappe
from frappe.utils.password import update_password

def execute():
    # Fetch all active users, excluding Administrator and Guest
    users = frappe.get_all("User", filters={"enabled": 1, "name": ["not in", ["Administrator", "Guest"]]})

    new_password = "iitg@123"

    for user in users:
        update_password(user.name, new_password)
        print(f"Password updated for: {user.name}")

    frappe.db.commit()


# bench --site prornd.local execute rndopsapp.resetPassword.execute



# db_name=$(cat sites/prornd.local/site_config.json | grep -oP '"db_name": "\K[^"]+')
# db_password=$(cat sites/prornd.local/site_config.json | grep -oP '"db_password": "\K[^"]+')

# mysqldump -u "$db_name" -p"$db_password" "$db_name" tabUser --where="name != 'Administrator'" > User.sql


# import
#  bench --site prornd.local mariadb < User.sql