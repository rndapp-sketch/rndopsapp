# Copyright (c) 2025, rndops and contributors
# Kafka Configuration - Centralized configuration for all Kafka operations

# --- KAFKA CLUSTER CONFIGURATION ---
# 2-Node Fault-Tolerant Cluster
KAFKA_BOOTSTRAP_SERVERS = [
    '172.16.134.81:9095',
    '172.16.134.81:9096'
]

# --- TOPIC CONFIGURATION ---
NUM_PARTITIONS = 2
REPLICATION_FACTOR = 2

# --- PRODUCER TOPICS ---
TOPIC_PROJECT = 'project-registration-events'
TOPIC_SANCTION = 'fund-sanction-events'
TOPIC_FUND_RECEIVED = 'fund-received-events'
TOPIC_DEPOSIT_SLIP = 'deposit-slip-events'
TOPIC_LOAN_REQUEST = 'loan-request-event'

# --- PRODUCER DLQ TOPICS ---
TOPIC_PROJECT_DLQ = 'project-registration-events-dlq'
TOPIC_SANCTION_DLQ = 'fund-sanction-events-dlq'
TOPIC_FUND_RECEIVED_DLQ = 'fund-received-events-dlq'
TOPIC_DEPOSIT_SLIP_DLQ = 'deposit-slip-events-dlq'
TOPIC_LOAN_REQUEST_DLQ = 'loan-request-event-dlq'

# --- CONSUMER TOPICS ---
TOPIC_ACCOUNTS_FUND_RECEIVED = 'accounts-fundreceived-update'
TOPIC_DEPOSIT_SLIP_UPDATE = 'accounts-depositslip-update'

# DLQ published by the external ledger microservice's AccountHeadPayment
# Consumer when it can't process an account-head-payment-events message
# (e.g. "Advance settlement payment requires parent commit amount and bill
# amount"). We consume it here purely to surface the failure to the frontend.
TOPIC_ACCOUNT_HEAD_PAYMENT_DLQ = 'account-head-payment-events-dlq'

# All Producer Topics List
ALL_PRODUCER_TOPICS = [
    TOPIC_PROJECT, TOPIC_PROJECT_DLQ,
    TOPIC_SANCTION, TOPIC_SANCTION_DLQ,
    TOPIC_FUND_RECEIVED, TOPIC_FUND_RECEIVED_DLQ,
    TOPIC_DEPOSIT_SLIP, TOPIC_DEPOSIT_SLIP_DLQ,
    TOPIC_LOAN_REQUEST, TOPIC_LOAN_REQUEST_DLQ,
]

# All Consumer Topics List
ALL_CONSUMER_TOPICS = [
    TOPIC_ACCOUNTS_FUND_RECEIVED,
    TOPIC_DEPOSIT_SLIP_UPDATE,
    TOPIC_ACCOUNT_HEAD_PAYMENT_DLQ,
]

# --- SCHEMA VERSIONS ---
SCHEMA_VERSION_PROJECT = '1.0'
SCHEMA_VERSION_SANCTION = '1.0'
SCHEMA_VERSION_FUND_RECEIVED = '1.0'
SCHEMA_VERSION_DEPOSIT_SLIP = '1.0'
SCHEMA_VERSION_LOAN_REQUEST = '1.0'

# --- PRODUCER RETRY CONFIGURATION ---
PRODUCER_MAX_RETRIES = 3
PRODUCER_RETRY_DELAY_SECONDS = 1  # Exponential backoff base
PRODUCER_ACKS = "all"  # Wait for all replicas
PRODUCER_RETRIES = 3
PRODUCER_LINGER_MS = 10  # Small batch window for better throughput

# --- CONSUMER CONFIGURATION ---
CONSUMER_GROUP_ID = 'rndopsapp-consumer-group-v2'
CONSUMER_AUTO_OFFSET_RESET = 'earliest'
CONSUMER_ENABLE_AUTO_COMMIT = True
CONSUMER_AUTO_COMMIT_INTERVAL_MS = 5000
CONSUMER_SESSION_TIMEOUT_MS = 30000
CONSUMER_HEARTBEAT_INTERVAL_MS = 10000
CONSUMER_MAX_POLL_RECORDS = 100
CONSUMER_MAX_POLL_INTERVAL_MS = 300000
CONSUMER_MAX_RETRIES = 3
CONSUMER_RETRY_DELAY_SECONDS = 1
