# Copyright (c) 2025, rndops and contributors
# Kafka Consumer Handler - Orchestrates background threads and message processing loops
# This file provides the main entry points for Kafka consumption using the modular handlers.

import os
import json
import time
import threading
from datetime import datetime
import frappe
from typing import Optional, List

from .config import (
    KAFKA_BOOTSTRAP_SERVERS,
    CONSUMER_GROUP_ID,
    ALL_CONSUMER_TOPICS,
    CONSUMER_MAX_POLL_RECORDS,
    CONSUMER_RETRY_DELAY_SECONDS,
)
from .logs.logger import get_consumer_logger, get_error_logger, log_consumer_event
from .consumer.handler import process_message

# Loggers
kafka_logger = get_consumer_logger()
error_logger = get_error_logger()

# Check if Kafka dependencies are available
try:
    from kafka import KafkaConsumer, TopicPartition
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    print("ERROR: kafka-python library not installed")

# Singleton instance management
_consumer = None
_consumer_thread = None
_stop_consumer = threading.Event()

def get_consumer():
    """
    Returns a singleton KafkaConsumer instance.
    Uses proper group_id to enable offset commits.
    """
    global _consumer

    if not KAFKA_AVAILABLE:
        error_logger.error("kafka-python library not installed")
        return None

    if _consumer is not None:
        return _consumer

    try:
        print("DEBUG: Creating new KafkaConsumer...")
        # Create consumer WITH group_id to enable offset management
        _consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=CONSUMER_GROUP_ID,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=False,  # We will commit manually
            max_poll_records=CONSUMER_MAX_POLL_RECORDS
        )

        all_topic_partitions = []
        for topic in ALL_CONSUMER_TOPICS:
            partitions = _consumer.partitions_for_topic(topic)
            if partitions:
                all_topic_partitions.extend([TopicPartition(topic, p) for p in partitions])
                print(f"DEBUG: Found {len(partitions)} partitions for topic {topic}")
            else:
                kafka_logger.warning(f"No partitions found for topic {topic}")

        if all_topic_partitions:
            _consumer.assign(all_topic_partitions)
            print(f"DEBUG: Manually assigned {len(all_topic_partitions)} partitions with group_id based offset management")
            kafka_logger.info(f"Manually assigned {len(all_topic_partitions)} partitions")
            
            # Note: We do NOT call seek_to_beginning() here anymore.
            # This allows the consumer to resume from the last committed offset.
        else:
            error_logger.error(f"No partitions found for any topic in {ALL_CONSUMER_TOPICS}")
            return None

        return _consumer
    except Exception as e:
        error_logger.error(f"Failed to connect Kafka Consumer: {str(e)}")
        return None

def close_consumer():
    """
    Closes the singleton consumer instance effectively.
    """
    global _consumer
    if _consumer is not None:
        try:
            _consumer.close()
            kafka_logger.info("Kafka Consumer closed successfully")
        except Exception as e:
            error_logger.error(f"Error closing Kafka Consumer: {str(e)}")
        finally:
            _consumer = None

def check_db_connection():
    """
    Checks if database connection is alive and reconnects if needed.
    """
    try:
        if frappe.db:
            frappe.db.sql("SELECT 1")
            return True
    except Exception:
        pass
    
    # Try to reconnect
    try:
        frappe.connect()
        frappe.db.sql("SELECT 1")
        print("DEBUG: Reconnected to database")
        return True
    except Exception as e:
        error_logger.error(f"Database connection failed: {e}")
        return False

def ensure_frappe_site_init():
    """
    Ensures Frappe site is properly initialized for the current thread.
    Required for background threads that need database access.
    """
    try:
        if frappe.local and hasattr(frappe.local, 'site') and frappe.local.site:
            return check_db_connection()

        site_name = os.environ.get('FRAPPE_SITE')
        if not site_name:
            # Fallback for determining site name in local dev
            sites_path = os.environ.get('SITES_PATH') or '.'
            for d in os.listdir(sites_path):
                if os.path.isdir(os.path.join(sites_path, d)) \
                   and not d.startswith('.') \
                   and d not in ('assets', 'logs'):
                    site_name = d
                    break

        if not site_name:
            print("ERROR: Could not determine Frappe site name")
            return False

        frappe.init(site=site_name)
        frappe.connect()
        print(f"DEBUG: Initialized Frappe site: {site_name}")
        return True
    except Exception as e:
        print(f"ERROR: Failed to initialize Frappe site: {str(e)}")
        return False

def process_message_with_context(topic, message_value, partition=None, offset=None):
    """
    Wrapper to process message with proper Frappe context.
    Ensures database connection is active before processing.
    """
    try:
        if not check_db_connection():
            error_logger.error("Failed to establish DB connection for message processing")
            return False

        # Route to modular handlers
        success = process_message(topic, message_value)

        # Logging
        msg_info = f"Topic: {topic} | Partition: {partition} | Offset: {offset}"
        if success:
            kafka_logger.info(f"SUCCESS: {msg_info}")
        else:
            error_logger.error(f"FAILED: {msg_info}")

        return success
    except Exception as e:
        error_logger.error(f"Exception in process_message_with_context: {str(e)}")
        try:
            frappe.db.rollback()
        except:
            pass
        return False

def start_consumer_loop():
    """
    Starts an infinite consumer loop in a background thread.
    Includes robust reconnection logic and error handling.
    """
    global _stop_consumer
    _stop_consumer.clear()

    if not ensure_frappe_site_init():
        error_logger.error("Failed to initialize Frappe site for consumer thread")
        return False

    kafka_logger.info("Starting Kafka consumer loop with auto-reconnect...")
    print("DEBUG: Starting Kafka consumer loop with auto-reconnect...")

    while not _stop_consumer.is_set():
        # Outer loop for connection management
        consumer = get_consumer()
        if not consumer:
            print("DEBUG: Consumer creation failed, retrying in 5s...")
            time.sleep(5)
            continue
            
        try:
            # Inner loop for message processing
            poll_count = 0
            while not _stop_consumer.is_set():
                if not check_db_connection():
                     print("DEBUG: DB connection lost, breaking inner loop to reconnect...")
                     break

                poll_count += 1
                if poll_count % 60 == 0:  # Log heartbeat every ~60 polls
                    print(f"DEBUG: Consumer heartbeat | {datetime.now()}")

                # Poll for messages
                message_batch = consumer.poll(timeout_ms=1000, max_records=CONSUMER_MAX_POLL_RECORDS)

                if message_batch:
                    count = sum(len(m) for m in message_batch.values())
                    print(f"DEBUG: Processing batch of {count} messages")
                    
                    # Process batch
                    for topic_partition, messages in message_batch.items():
                        for message in messages:
                            if _stop_consumer.is_set():
                                break
                            
                            process_message_with_context(
                                topic_partition.topic, 
                                message.value, 
                                message.partition, 
                                message.offset
                            )
                    
                    # Commit offsets after successful batch processing
                    try:
                        consumer.commit()
                        kafka_logger.info("Offsets committed successfully")
                    except Exception as commit_err:
                        error_logger.error(f"Failed to commit offsets: {commit_err}")

        except KafkaError as ke:
            error_logger.error(f"Kafka Error in consumer loop: {ke}")
            print(f"ERROR: Kafka Error: {ke}")
        except Exception as e:
            error_logger.error(f"Unexpected error in consumer loop: {e}")
            print(f"ERROR: Unexpected error: {e}")
        finally:
            # Force close consumer to reset connection state before retrying
            print("DEBUG: Closing consumer before reconnecting...")
            close_consumer()
            
            # Wait before reconnecting to avoid tight loops
            if not _stop_consumer.is_set():
                time.sleep(CONSUMER_RETRY_DELAY_SECONDS)

    print("DEBUG: Kafka consumer loop stopped gracefully")
    return True

# ==========================================
# Frappe Whitelisted Methods
# ==========================================

@frappe.whitelist()
def start_kafka_consumer():
    """
    Frappe whitelisted method to start the Kafka consumer.
    """
    global _consumer_thread

    if _consumer_thread is not None and _consumer_thread.is_alive():
        return {"status": "warning", "message": "Kafka consumer thread is already running"}

    _consumer_thread = threading.Thread(
        target=start_consumer_loop,
        name="KafkaConsumerThread",
        daemon=True
    )
    _consumer_thread.start()
    kafka_logger.info("Kafka consumer thread started")
    return {"status": "success", "message": "Kafka consumer started"}

@frappe.whitelist()
def stop_kafka_consumer():
    """
    Frappe whitelisted method to stop the Kafka consumer.
    """
    global _stop_consumer
    _stop_consumer.set()
    return {"status": "success", "message": "Kafka consumer stop sign sent"}

@frappe.whitelist()
def get_kafka_consumer_status():
    """
    Frappe whitelisted method to get consumer status.
    """
    global _consumer, _consumer_thread
    
    status = {
        "kafka_available":KAFKA_AVAILABLE,
        "consumer_connected": _consumer is not None,
        "consumer_thread_running": _consumer_thread is not None and _consumer_thread.is_alive(),
        "subscribed_topics": ALL_CONSUMER_TOPICS,
        "consumer_group_id": CONSUMER_GROUP_ID,
        "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
        "db_connection": False
    }
    
    # Check DB status too
    try:
        if frappe.db:
            frappe.db.sql("SELECT 1")
            status["db_connection"] = True
    except:
        pass
        
    return status

@frappe.whitelist()
def consume_kafka_messages(max_messages=10):
    """
    Frappe whitelisted method to consume a specific number of messages manually.
    WARNING: This skips the main loop logic! Use for debugging only.
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
        
        # Determine if we should commit manually here too
        try:
             consumer.commit()
        except:
             pass

        return {"status": "success", "messages_processed": processed}
    except Exception as e:
        error_logger.error(f"Manual consume failed: {str(e)}")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def reset_consumer_offset_to_beginning():
    """
    Frappe whitelisted method to reset consumer offset to beginning (offset 0).
    """
    try:
        # Close global consumer if open to avoid conflicts
        close_consumer()

        # Create a fresh consumer to reset offsets
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

        if not all_tps:
            consumer.close()
            return {"status": "error", "message": f"No partitions found for topics: {ALL_CONSUMER_TOPICS}"}

        # Assign and seek
        consumer.assign(all_tps)
        consumer.seek_to_beginning()

        # Commit (saves the reset position to the group)
        consumer.commit()
        consumer.close()

        kafka_logger.info(f"Offsets reset for {len(all_tps)} partitions across {len(topics_found)} topics")
        return {
            "status": "success",
            "message": f"Offsets reset for {len(all_tps)} partitions across {len(topics_found)} topics",
            "topics": topics_found
        }
    except Exception as e:
        error_logger.error(f"Error resetting consumer offset: {str(e)}")
        return {"status": "error", "message": str(e)}
