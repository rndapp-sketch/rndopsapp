"""
Centralized configuration for all static IPs and service URLs.
This file consolidates all hardcoded IP addresses used throughout the application.
"""

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = [
    '172.16.134.81:9095',
    '172.16.134.81:9096',
    '172.16.135.118:9097'
]

# Mattermost Configuration
MATTERMOST_BASE_URL = "http://172.16.135.118:8065"
MATTERMOST_API_URL = f"{MATTERMOST_BASE_URL}/api/v4"
MATTERMOST_POSTS_URL = f"{MATTERMOST_API_URL}/posts"

# Account Portal Configuration
ACCOUNT_PORTAL_BASE_URL = "http://172.16.134.81:18080"
ACCOUNT_PORTAL_API = f"{ACCOUNT_PORTAL_BASE_URL}/api"

# Account Portal Endpoints
ACCOUNT_PORTAL_SANCTION_DETAILS = f"{ACCOUNT_PORTAL_API}/sanction-details/addSanctionDetails"
ACCOUNT_PORTAL_COMMIT_PAYMENT = f"{ACCOUNT_PORTAL_API}/commit-payment-transactions"
ACCOUNT_PORTAL_ACCOUNT_HEAD_PAYMENTS = f"{ACCOUNT_PORTAL_API}/account-head-payments"
ACCOUNT_PORTAL_ACCOUNT_HEAD_COMMIT = f"{ACCOUNT_PORTAL_API}/account-head-commit"
ACCOUNT_PORTAL_ACCOUNT_HEAD_COMMIT_STATUS = f"{ACCOUNT_PORTAL_API}/account-head-commit/status/by-project-frap"
ACCOUNT_PORTAL_ACCOUNT_HEAD_REF_DETAILS = f"{ACCOUNT_PORTAL_API}/account-head-commit/ref-details"
ACCOUNT_PORTAL_PROJECTS = f"{ACCOUNT_PORTAL_API}/projects"
ACCOUNT_PORTAL_PROJECTS_CHANGE_NUMBER = f"{ACCOUNT_PORTAL_API}/projects"  # Used with {project_no}/change-project-number path
ACCOUNT_PORTAL_FUND_RECEIVED = f"{ACCOUNT_PORTAL_API}/fund-received/addFundReceived"
ACCOUNT_PORTAL_ACCOUNT_HEADS = f"{ACCOUNT_PORTAL_API}/account-heads/createAccountHead"

# Minio Configuration
MINIO_ENDPOINT = "172.16.135.118:9000"
MINIO_URL = f"http://{MINIO_ENDPOINT}"

# Ollama Configuration
OLLAMA_BASE_URL = "http://172.16.117.154:11434"

# External Auth Configuration
EXTERNAL_AUTH_URL = "http://172.16.135.27:3001/auth/login"

# S3 Credentials Endpoint (Minio)
S3_CREDENTIALS_ENDPOINT = "http://172.16.135.118:9001/api/v1/service-account-credentials"

# API Methods
API_DISBURSAL_URL = "http://172.16.134.81:8000/api/method/rndopsapp.rndopsapp.doctype.disbursal_of_honorarium.disbursal_of_honorarium.save_disbursal_of_honorarium_data"

# Chatwoot Configuration
CHATWOOT_BASE_URL = "http://172.16.135.118:8066"
