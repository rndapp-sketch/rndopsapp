bench --site prornd.local mariadb --execute "UPDATE `tabRecruitment Adhoc Contractual` SET workflow_state = 'Pending Head Approval', docstatus = 1 WHERE name = '202604150A00297'; SELECT name, workflow_state, docstatus FROM `tabRecruitment Adhoc Contractual` WHERE name = '202604150A00297';" 2>/dev/null


