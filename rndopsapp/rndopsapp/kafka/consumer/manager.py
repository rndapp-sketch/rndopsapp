# Copyright (c) 2025, rndops and contributors
# Kafka Consumer Manager - Orchestrates background threads and message processing loops

import os
import json
import time
import threading
import frappe
from typing import Optional, List

from ..config import (
    KAFKA_BOOTSTRAP_SERVERS,
    CONSUMER_GROUP_ID,
    ALL_CONSUMER_TOPICS,
    NEW_DLQ_CONSUMER_TOPICS,
    CONSUMER_MAX_POLL_RECORDS,
    CONSUMER_RETRY_DELAY_SECONDS,
)
from ..logs import log_consumer_event, log_error, log_info, log_warning
from .handler import process_message

# Check if Kafka depends are available
try:
    from kafka import KafkaConsumer, TopicPartition
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

# Singleton instance management
_consumer = None
_consumer_thread = None
_stop_consumer = threading.Event()

# Redis keys — shared across all Gunicorn workers
_HEARTBEAT_KEY = "kafka_consumer_heartbeat"
_HEARTBEAT_TTL = 15  # seconds — if no heartbeat for this long, consumer is considered dead
_HEARTBEAT_INTERVAL = 5  # seconds between heartbeats written by the consumer loop


def _write_heartbeat():
    """Called from the consumer loop thread to mark itself alive in Redis."""
    try:
        import time as _time
        frappe.cache().set_value(_HEARTBEAT_KEY, _time.time(), expires_in_sec=_HEARTBEAT_TTL)
    except Exception:
        pass


def _clear_heartbeat():
    """Called when the consumer loop exits cleanly."""
    try:
        frappe.cache().delete_value(_HEARTBEAT_KEY)
    except Exception:
        pass


def is_consumer_running_globally() -> bool:
    """
    Returns True if a consumer heartbeat exists in Redis (fresh within TTL).
    Safe to call from any Gunicorn worker — does not rely on per-process thread state.
    """
    try:
        return bool(frappe.cache().get_value(_HEARTBEAT_KEY))
    except Exception:
        # Fall back to local thread check if Redis unavailable
        return _consumer_thread is not None and _consumer_thread.is_alive()


def get_consumer():
    """Returns a singleton KafkaConsumer instance with manual assignment."""
    global _consumer

    if not KAFKA_AVAILABLE:
        log_error("kafka-python library not installed", "KAFKA_IMPORT_ERROR")
        return None

    if _consumer is not None:
        return _consumer

    try:
        # Create consumer WITHOUT group_id for manual assignment
        _consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=False,  # Manual assignment doesn't use commit in the same way
            max_poll_records=CONSUMER_MAX_POLL_RECORDS
        )

        all_topic_partitions = []
        for topic in ALL_CONSUMER_TOPICS:
            partitions = _consumer.partitions_for_topic(topic)
            if partitions:
                all_topic_partitions.extend([TopicPartition(topic, p) for p in partitions])
                log_info(f"Found {len(partitions)} partitions for topic: {topic}", "consumer")
            else:
                log_warning(f"No partitions found for topic: {topic}", "consumer")

        if all_topic_partitions:
            _consumer.assign(all_topic_partitions)
            # Default to beginning for early testing/dev as per user's previous code
            _consumer.seek_to_beginning()

            # The DLQ topics just added to ALL_CONSUMER_TOPICS already have a
            # backlog that predates this consumer (they had no consumer at
            # all before). Skip straight to the current end for just those
            # topic-partitions so that backlog is never auto-processed —
            # only failures from here on are. The topics above keep their
            # existing beginning-replay behavior unchanged.
            new_dlq_tps = [tp for tp in all_topic_partitions if tp.topic in NEW_DLQ_CONSUMER_TOPICS]
            if new_dlq_tps:
                _consumer.seek_to_end(*new_dlq_tps)
                log_info(f"Seeked {len(new_dlq_tps)} new DLQ partitions to end (skipping backlog)", "consumer")

            log_info(f"Assigned {len(all_topic_partitions)} partitions and seeked to beginning", "consumer")
        else:
            log_error(f"No partitions found for any topic in {ALL_CONSUMER_TOPICS}", "KAFKA_CONFIG_ERROR")
            return None

        return _consumer
    except Exception as e:
        log_error(f"Failed to connect Kafka Consumer: {str(e)}", "KAFKA_CONNECTION_ERROR")
        return None


def close_consumer():
    """Closes and resets the consumer singleton."""
    global _consumer
    if _consumer:
        try:
            _consumer.close()
            log_info("Kafka Consumer closed successfully", "consumer")
        except Exception as e:
            log_error(f"Error closing Kafka Consumer: {str(e)}", "KAFKA_CLOSE_ERROR")
        finally:
            _consumer = None


def ensure_frappe_site_init():
    """Ensures Frappe site is properly initialized for the current thread."""
    try:
        # Check if site is already initialized
        if frappe.local and hasattr(frappe.local, 'site') and frappe.local.site:
            if not frappe.db:
                frappe.connect()
            else:
                # Verify the connection is still alive — MySQL silently drops idle
                # connections after wait_timeout, which causes InterfaceError (0, '').
                try:
                    frappe.db.sql("SELECT 1")
                except Exception:
                    frappe.connect()
            return True

        # Try to determine site name
        site_name = os.environ.get('FRAPPE_SITE')
        if not site_name and hasattr(frappe.local, 'site'):
             site_name = frappe.local.site

        if not site_name:
            # Fallback for local dev environments
            sites_path = os.environ.get('SITES_PATH') or '.'
            sites = [d for d in os.listdir(sites_path)
                    if os.path.isdir(os.path.join(sites_path, d))
                    and not d.startswith('.')
                    and d not in ('assets', 'logs')]
            if sites:
                site_name = sites[0]

        if not site_name:
            return False

        frappe.init(site=site_name)
        frappe.connect()
        return True
    except Exception as e:
        print(f"ERROR: Failed to initialize Frappe site: {str(e)}")
        return False


def process_message_with_context(topic, message_value, partition, offset):
    """Wrapper to process message with proper Frappe context and logging."""
    try:
        if not ensure_frappe_site_init():
            return False

        success = process_message(topic, message_value)

        if success:
             log_consumer_event("CONSUME", "N/A", topic, "SUCCESS",
                              f"Partition: {partition} | Offset: {offset}",
                              partition=partition, offset=offset)
        else:
             log_consumer_event("CONSUME", "N/A", topic, "FAILED",
                              f"Failed processing partition: {partition} | offset: {offset}",
                              partition=partition, offset=offset)

        return success
    except Exception as e:
        log_error(f"Exception in process_message_with_context: {str(e)}", "CONSUME_ERROR")
        try:
            frappe.db.rollback()
        except:
            pass
        return False


def start_consumer_loop():
    """Main consumer loop running in a background thread."""
    global _stop_consumer
    _stop_consumer.clear()

    if not ensure_frappe_site_init():
        log_error("Failed to initialize Frappe site for consumer thread", "INIT_ERROR")
        return False

    consumer = get_consumer()
    if not consumer:
        return False

    log_info("Starting Kafka consumer loop...", "consumer")
    poll_count = 0
    last_heartbeat = 0.0

    try:
        while not _stop_consumer.is_set():
            try:
                poll_count += 1
                now = time.monotonic()

                # Write heartbeat to Redis every HEARTBEAT_INTERVAL seconds
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                    _write_heartbeat()
                    last_heartbeat = now

                message_batch = consumer.poll(timeout_ms=1000, max_records=CONSUMER_MAX_POLL_RECORDS)

                if not message_batch:
                    continue

                for topic_partition, messages in message_batch.items():
                    topic = topic_partition.topic
                    for message in messages:
                        if _stop_consumer.is_set():
                            break
                        process_message_with_context(topic, message.value, message.partition, message.offset)

            except Exception as e:
                if not _stop_consumer.is_set():
                    log_error(f"Consumer loop error: {str(e)}", "LOOP_ERROR")
                    time.sleep(CONSUMER_RETRY_DELAY_SECONDS)

    except Exception as e:
        log_error(f"Consumer loop terminated: {str(e)}", "TERMINAL_ERROR")
    finally:
        _clear_heartbeat()
        close_consumer()

    log_info("Kafka consumer loop stopped", "consumer")
    return True


@frappe.whitelist()
def start_kafka_consumer():
    """Frappe whitelisted method to start the Kafka consumer."""
    global _consumer_thread
    if _consumer_thread is not None and _consumer_thread.is_alive():
        return {"status": "warning", "message": "Consumer thread already running"}

    _consumer_thread = threading.Thread(
        target=start_consumer_loop,
        name="KafkaConsumerThread",
        daemon=True
    )
    _consumer_thread.start()
    return {"status": "success", "message": "Kafka consumer thread started"}


@frappe.whitelist()
def stop_kafka_consumer():
    """Frappe whitelisted method to stop the Kafka consumer."""
    global _stop_consumer
    _stop_consumer.set()
    return {"status": "success", "message": "Stop signal sent to consumer"}


@frappe.whitelist()
def get_kafka_consumer_status():
    """Returns the current status of the Kafka consumer."""
    return {
        "running": is_consumer_running_globally(),
        "topics": ALL_CONSUMER_TOPICS,
        "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
        "group_id": CONSUMER_GROUP_ID,
        "kafka_available": KAFKA_AVAILABLE
    }


@frappe.whitelist()
def reset_consumer_offset_to_beginning():
    """
    Frappe whitelisted method to reset consumer offset to beginning (offset 0).
    Resets offsets for ALL topics in ALL_CONSUMER_TOPICS.
    """
    if not KAFKA_AVAILABLE:
        return {"status": "error", "message": "Kafka library not available"}

    try:
        # Close global consumer if open to avoid conflicts
        close_consumer()

        # Temporary consumer for reset
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=CONSUMER_GROUP_ID,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=True
        )

        all_tps = []
        topics_found = []

        for topic in ALL_CONSUMER_TOPICS:
            partition_ids = consumer.partitions_for_topic(topic)
            if partition_ids:
                tps = [TopicPartition(topic, p) for p in partition_ids]
                all_tps.extend(tps)
                topics_found.append(topic)
                log_info(f"Reset: Found {len(partition_ids)} partitions for topic {topic}", "consumer")

        if not all_tps:
            consumer.close()
            return {"status": "error", "message": f"No partitions found for any topic in {ALL_CONSUMER_TOPICS}"}

        # Assign and seek
        consumer.assign(all_tps)
        consumer.seek_to_beginning()

        # Commit (this saves the earliest offsets to the group)
        consumer.commit()
        consumer.close()

        log_info(f"Offsets successfully reset to beginning for {len(all_tps)} partitions", "consumer")
        return {
            "status": "success",
            "message": f"Offsets reset to beginning for {len(all_tps)} partitions across {len(topics_found)} topics",
            "topics": topics_found
        }
    except Exception as e:
        log_error(f"Error resetting consumer offset: {str(e)}", "OFFSET_RESET_ERROR")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def consume_kafka_messages(max_messages=10):
    """
    Frappe whitelisted method to consume a specific number of messages manually.
    """
    try:
        max_messages = int(max_messages)
        consumer = get_consumer()
        if not consumer:
            return {"status": "error", "message": "Consumer not available"}

        processed = 0
        message_batch = consumer.poll(timeout_ms=5000, max_records=max_messages)

        for topic_partition, messages in message_batch.items():
            topic = topic_partition.topic
            for message in messages:
                if processed >= max_messages:
                    break
                process_message_with_context(topic, message.value, message.partition, message.offset)
                processed += 1

        return {
            "status": "success",
            "messages_processed": processed
        }
    except Exception as e:
        log_error(f"Manual consume failed: {str(e)}", "MANUAL_CONSUME_ERROR")
        return {"status": "error", "message": str(e)}
