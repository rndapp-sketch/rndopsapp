# Copyright (c) 2025, rndops and contributors
# Kafka Consumer Service - Central entry point for all Kafka consumer operations

import frappe
from .log_reader import get_kafka_logs


@frappe.whitelist()
def fetch_kafka_logs(log_type='consumer', lines=50, search_string=None):
	"""
	Fetches the last N lines of the specified Kafka log.
	Allowed types: consumer, producer, error, debug, frappe, terminal.
	Optionally filters by search_string.
	"""
	return get_kafka_logs(log_type, lines, search_string)


@frappe.whitelist()
def start_kafka_consumer(**kwargs):
	from .consumer.manager import start_kafka_consumer as _fn
	return _fn()


@frappe.whitelist()
def stop_kafka_consumer(**kwargs):
	from .consumer.manager import stop_kafka_consumer as _fn
	return _fn()


@frappe.whitelist()
def get_kafka_consumer_status(**kwargs):
	from .consumer.manager import get_kafka_consumer_status as _fn
	return _fn()


@frappe.whitelist()
def reset_consumer_offset_to_beginning(**kwargs):
	from .consumer.manager import reset_consumer_offset_to_beginning as _fn
	return _fn()


@frappe.whitelist()
def consume_kafka_messages(max_messages=10, **kwargs):
	from .consumer.manager import consume_kafka_messages as _fn
	return _fn(max_messages=max_messages)


__all__ = [
	"start_kafka_consumer",
	"stop_kafka_consumer",
	"get_kafka_consumer_status",
	"reset_consumer_offset_to_beginning",
	"consume_kafka_messages",
	"fetch_kafka_logs",
]
