# Copyright (c) 2025, rndops and contributors
# Kafka Consumer Module

from .manager import (
    start_kafka_consumer,
    stop_kafka_consumer,
    get_kafka_consumer_status,
)
from .handler import process_message

__all__ = [
    "start_kafka_consumer",
    "stop_kafka_consumer",
    "get_kafka_consumer_status",
    "process_message",
]
