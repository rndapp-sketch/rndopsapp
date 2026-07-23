# Copyright (c) 2025, rndops and contributors
# Kafka Module - Centralized Kafka Producer and Consumer Infrastructure
#
# This module provides a modular, organized structure for Kafka operations:
# - producer/: All Kafka producer modules (project_registration, fund_sanction, etc.)
# - consumer/: All Kafka consumer modules (fund_received, deposit_slip, etc.)
# - logs/: Centralized logging infrastructure for Kafka operations
#
# Usage:
#   from rndopsapp.rndopsapp.kafka.producer.project_registration import publish_project_registration
#   from rndopsapp.rndopsapp.kafka.consumer.fund_received import handle_fund_received_update

__version__ = "1.0.0"
