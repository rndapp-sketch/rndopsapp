# Copyright (c) 2025, rndops and contributors
# Kafka Consumer Service - Central entry point for all Kafka consumer operations

from .consumer.manager import (
    start_kafka_consumer,
    stop_kafka_consumer,
    get_kafka_consumer_status,
    reset_consumer_offset_to_beginning,
    consume_kafka_messages,
)
from .log_reader import get_kafka_logs
import frappe

@frappe.whitelist()
def fetch_kafka_logs(log_type='consumer', lines=50, search_string=None):
    """
    Fetches the last N lines of the specified Kafka log.
    Allowed types: consumer, producer, error, debug, frappe, terminal.
    Optionally filters by search_string.
    """
    return get_kafka_logs(log_type, lines, search_string)

__all__ = [
    "start_kafka_consumer",
    "stop_kafka_consumer",
    "get_kafka_consumer_status",
    "reset_consumer_offset_to_beginning",
    "consume_kafka_messages",
    "fetch_kafka_logs",
]
