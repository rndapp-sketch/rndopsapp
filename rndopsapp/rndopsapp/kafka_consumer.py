# import frappe
# import json
# import time
# import threading
# from datetime import datetime
# from frappe import _

# try:
#     from kafka import KafkaConsumer
#     from kafka.errors import KafkaError
#     KAFKA_AVAILABLE = True
# except ImportError:
#     KAFKA_AVAILABLE = False


# # --- CONFIGURATION ---
# # Kafka Cluster-A ONLY (topic exists here)
# KAFKA_BOOTSTRAP_SERVERS = [
#     '172.16.134.81:9095',
#     '172.16.134.81:9096'
# ]

# # Consumer Group ID
# CONSUMER_GROUP_ID = 'rndopsapp-consumer-group-v2'

# # Topic to consume
# TOPIC_ACCOUNTS_FUND_RECEIVED = 'accounts-fundreceived-update'

# # =============================================================================
# # [ADDED] Deposit Slip Update Topic - Receives updates from colleague's system
# # =============================================================================
# TOPIC_DEPOSIT_SLIP_UPDATE = 'accounts-depositslip-update'

# # All Topics to Consume
# CONSUME_TOPICS = [
#     TOPIC_ACCOUNTS_FUND_RECEIVED,
#     TOPIC_DEPOSIT_SLIP_UPDATE,  # [ADDED] Deposit Slip Update Topic
# ]

# # Consumer Configuration
# AUTO_OFFSET_RESET = 'earliest'  # Start from earliest if no committed offset
# ENABLE_AUTO_COMMIT = True
# AUTO_COMMIT_INTERVAL_MS = 5000  # Commit offsets every 5 seconds
# SESSION_TIMEOUT_MS = 30000
# HEARTBEAT_INTERVAL_MS = 10000
# MAX_POLL_RECORDS = 100
# MAX_POLL_INTERVAL_MS = 300000

# # Retry Configuration
# MAX_RETRIES = 3
# RETRY_DELAY_SECONDS = 1

# # Singleton Consumer Instance
# _consumer = None
# _consumer_thread = None
# _stop_consumer = threading.Event()


# def get_consumer():
#     """
#     Returns a singleton KafkaConsumer instance.
#     Reuses the same connection for all message consumption.
#     """
#     global _consumer

#     if not KAFKA_AVAILABLE:
#         print("ERROR: kafka-python library not installed")
#         frappe.log_error("kafka-python library not installed", "Kafka Consumer Error")
#         return None

#     if _consumer is not None:
#         return _consumer

#     try:
#         from kafka import TopicPartition
        
#         # Create consumer WITHOUT group_id (manual assign doesn't need group coordination)
#         _consumer = KafkaConsumer(
#             bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
#             # group_id=CONSUMER_GROUP_ID,  # Removed - conflicts with assign()
#             value_deserializer=lambda v: json.loads(v.decode('utf-8')),
#             auto_offset_reset=AUTO_OFFSET_RESET,
#             enable_auto_commit=False,  # No group, so no auto-commit
#             session_timeout_ms=SESSION_TIMEOUT_MS,
#             heartbeat_interval_ms=HEARTBEAT_INTERVAL_MS,
#             max_poll_records=MAX_POLL_RECORDS,
#             max_poll_interval_ms=MAX_POLL_INTERVAL_MS
#         )
        
#         # Manually assign partitions (bypasses group coordinator)
#         # =============================================================================
#         # [UPDATED] Now assigns partitions for ALL topics in CONSUME_TOPICS
#         # =============================================================================
#         all_topic_partitions = []

#         for topic in CONSUME_TOPICS:
#             print(f"DEBUG: Getting partitions for topic: {topic}")
#             partitions = _consumer.partitions_for_topic(topic)

#             if partitions:
#                 tps = [TopicPartition(topic, p) for p in partitions]
#                 all_topic_partitions.extend(tps)
#                 print(f"DEBUG: Found {len(partitions)} partitions for topic {topic}")
#             else:
#                 print(f"WARNING: No partitions found for topic {topic} (topic may not exist yet)")

#         if all_topic_partitions:
#             _consumer.assign(all_topic_partitions)
#             print(f"DEBUG: Manually assigned {len(all_topic_partitions)} partitions: {all_topic_partitions}")

#             # Seek to beginning for fresh start
#             _consumer.seek_to_beginning()
#             print(f"DEBUG: Seeked to beginning of all partitions")

#             # Verify positions
#             for tp in all_topic_partitions:
#                 pos = _consumer.position(tp)
#                 print(f"DEBUG: Topic {tp.topic} Partition {tp.partition} position after seek: {pos}")
#         else:
#             print(f"ERROR: No partitions found for any topic in {CONSUME_TOPICS}")
        
#         print(f"DEBUG: Kafka Consumer connected to topics: {CONSUME_TOPICS}")
#         return _consumer
#     except Exception as e:
#         print(f"ERROR: Failed to connect Kafka Consumer: {str(e)}")
#         frappe.log_error(f"Failed to connect Kafka Consumer: {str(e)}", "Kafka Consumer Connection Error")
#         return None


# def close_consumer():
#     """
#     Closes the singleton consumer instance.
#     """
#     global _consumer
#     if _consumer is not None:
#         try:
#             _consumer.close()
#             print("DEBUG: Kafka Consumer closed successfully")
#             frappe.logger().info("Kafka Consumer closed successfully")
#         except Exception as e:
#             print(f"ERROR: Error closing Kafka Consumer: {str(e)}")
#             frappe.log_error(f"Error closing Kafka Consumer: {str(e)}", "Kafka Consumer Error")
#         finally:
#             _consumer = None


# def check_unconsumed_offset_zero():
#     """
#     Checks for unconsumed messages at offset 0 in the topic.
#     Resets offset to 0 if needed to consume from beginning.

#     [UPDATED] Now checks ALL topics in CONSUME_TOPICS
#     """
#     try:
#         consumer = get_consumer()
#         if not consumer:
#             frappe.logger().warning("Consumer not available for offset check")
#             return False

#         from kafka import TopicPartition

#         # =============================================================================
#         # [UPDATED] Check offset for ALL topics in CONSUME_TOPICS
#         # =============================================================================
#         for topic in CONSUME_TOPICS:
#             partitions = consumer.partitions_for_topic(topic)
#             if not partitions:
#                 frappe.logger().warning(f"No partitions found for topic: {topic}")
#                 continue

#             frappe.logger().info(f"Found partitions for {topic}: {partitions}")

#             # Check offset and committed offset for each partition
#             for partition in partitions:
#                 tp = TopicPartition(topic, partition)

#                 # Get committed offset
#                 committed_offset = consumer.committed(tp)
#                 frappe.logger().info(f"Topic {topic} Partition {partition} - Committed offset: {committed_offset}")

#                 # If no committed offset (None), it means we haven't consumed any messages
#                 if committed_offset is None:
#                     frappe.logger().info(
#                         f"No committed offset for {topic} partition {partition}. "
#                         f"Will consume from offset 0 (earliest)"
#                     )
#                     # Seek to beginning
#                     consumer.seek(tp, 0)
#                     frappe.logger().info(f"Seek to offset 0 for {topic} partition {partition}")

#         return True

#     except Exception as e:
#         frappe.log_error(
#             f"Error checking unconsumed offset 0: {str(e)}",
#             "Offset Check Error"
#         )
#         return False


# # ==========================================
# # Message Handlers
# # ==========================================

# def handle_accounts_fund_received_update(message):
#     """
#     Handler for accounts-fundreceived-update topic.
#     Processes incoming fund received update messages and creates/updates Frappe documents.
#     """
#     try:
#         data = message.get('data', {})
#         schema_version = message.get('schemaVersion', '1.0')
#         event_type = message.get('eventType', 'UNKNOWN')
#         timestamp = message.get('timestamp')
        
#         fund_received_ref_number = data.get('fundReceivedRefNumber')
#         fund_received_ref_number_fap = data.get('fundReceivedRefNumberFap')
#         sanction_letter_no = data.get('sanctionLetterNo')
#         project_number = data.get('projectNumber')
#         amount_received = data.get('amountReceived')
#         iitg_account_number = data.get('iitgAccountNumber')
#         deposit_slip_status = data.get('depositSlipStatus')
#         fund_received_status = data.get('fundReceivedStatus')
#         fund_budget_breakup_list = data.get('fundBudgetBreakupList', [])
#         transaction_details_list = data.get('transactionDetailsList', [])
        
#         print(f"Consumed Data: {json.dumps(data, indent=2)}")
#         frappe.logger().info(
#             f"Processing Accounts Fund Received Update: Ref# {fund_received_ref_number} | "
#             f"Project: {project_number} | Amount: {amount_received} | "
#             f"Status: {fund_received_status} | Event: {event_type}"
#         )
        
#         # Update Fund Received document (Update Only)
#         fund_received_doc = update_fund_received(
#             fund_received_ref_number=fund_received_ref_number,
#             fund_received_ref_number_fap=fund_received_ref_number_fap,
#             sanction_letter_no=sanction_letter_no,
#             project_number=project_number,
#             amount_received=amount_received,
#             iitg_account_number=iitg_account_number,
#             deposit_slip_status=deposit_slip_status,
#             fund_received_status=fund_received_status,
#             timestamp=timestamp
#         )
        
#         if fund_received_doc:
#             # Commit changes from update_fund_received before modifying child tables
#             frappe.db.commit()
            
#             # Process Fund Budget Breakup List
#             if fund_budget_breakup_list:
#                 create_fund_budget_breakup_items(
#                     fund_received_doc.name,
#                     fund_budget_breakup_list
#                 )
            
#             # Process Transaction Details List
#             if transaction_details_list:
#                 create_transaction_detail_items(
#                     fund_received_doc.name,
#                     transaction_details_list
#                 )
            
#             frappe.db.commit()
#             print(f"Successfully processed and updated: {fund_received_doc.name}")
#             return True
#         else:
#             print(f"Skipping: Fund Received document {fund_received_ref_number} not found.")
#             return True # Return True to commit offset even if doc not found

        
#     except Exception as e:
#         frappe.log_error(
#             f"Error processing accounts fund received update message: {str(e)}", 
#             "Kafka Consumer Handler Error"
#         )
#         return False


# def update_fund_received(**kwargs):
#     """
#     Updates an existing Fund Received document in Frappe.
    
#     Args:
#         fund_received_ref_number: Reference number (assumed to be doc ID/Name)
#         sanction_letter_no: Sanction letter number
#         project_number: Project number
#         amount_received: Amount received
#         iitg_account_number: IITG account number
#         deposit_slip_status: Status of deposit slip
#         fund_received_status: Status of fund received
#         timestamp: Timestamp of the event
        
#     Returns:
#         Fund Received document or None if not found/error
#     """
#     try:
#         fund_received_ref_number = kwargs.get('fund_received_ref_number')
#         fund_received_ref_number_fap = kwargs.get('fund_received_ref_number_fap')
        
#         # Check if document exists by Name (Ref Number FAP) - Primary lookup
#         if fund_received_ref_number_fap and frappe.db.exists('Fund Received', fund_received_ref_number_fap):
#              fund_received = frappe.get_doc('Fund Received', fund_received_ref_number_fap)
#         # Fallback: Check if document exists by Name (Ref Number)
#         elif frappe.db.exists('Fund Received', fund_received_ref_number):
#              fund_received = frappe.get_doc('Fund Received', fund_received_ref_number)
#         else:
#              # Fallback: Try to find by sanction letter and project
#              sanction_letter_no = kwargs.get('sanction_letter_no')
#              project_number = kwargs.get('project_number')
             
#              filters = {
#                  'sanctioned_letter_no': sanction_letter_no,
#                  'prjreg_title': project_number
#              }
#              found_name = frappe.db.get_value('Fund Received', filters, 'name')
             
#              if found_name:
#                  print(f"Found Fund Received by fallback lookup: {found_name}")
#                  fund_received = frappe.get_doc('Fund Received', found_name)
#              else:
#                  print(f"Fund Received document not found: {fund_received_ref_number} or via filters {filters}")
#                  frappe.logger().warning(f"Fund Received document not found: {fund_received_ref_number}")
#                  return None

#         print(f"DEBUG: Updating Fund Received: {fund_received.name}")
#         frappe.logger().info(f"Updating existing Fund Received: {fund_received.name}")
        
#         # Use frappe.db.set_value for direct DB updates (bypasses controller validations)
#         # This allows updating submitted documents
#         doc_name = fund_received.name
        
#         # Map sanction_letter_no
#         if kwargs.get('sanction_letter_no'):
#             frappe.db.set_value('Fund Received', doc_name, 'sanctioned_letter_no', kwargs.get('sanction_letter_no'))
        
#         # Map project_number to prjreg_title (Link Field)
#         if kwargs.get('project_number'):
#             frappe.db.set_value('Fund Received', doc_name, 'prjreg_title', kwargs.get('project_number'))
        
#         # Map amountReceived -> fund_received_amt
#         if kwargs.get('amount_received') is not None:
#             frappe.db.set_value('Fund Received', doc_name, 'fund_received_amt', kwargs.get('amount_received'))
        
#         # Map iitgAccountNumber -> bank_account
#         if kwargs.get('iitg_account_number'):
#             frappe.db.set_value('Fund Received', doc_name, 'bank_account', kwargs.get('iitg_account_number'))
        
#         # Map fundReceivedStatus -> workflow_state
#         fund_received_status = kwargs.get('fund_received_status')
#         if fund_received_status:
#             # Specific logic: If status is 'APPROVED' (case-insensitive), set to 'Pending Misc. Staff Approval(Deposit Slip Pending)'
#             if fund_received_status.upper() == 'APPROVED':
#                  new_status = 'Pending Misc. Staff Approval(Deposit Slip Pending)'
#             else:
#                  new_status = fund_received_status.title()
            
#             frappe.db.set_value('Fund Received', doc_name, 'workflow_state', new_status)
        
#         # Map fundReceivedRefNumber -> fund_received_ref_number (integer field)
#         if fund_received_ref_number is not None:
#             frappe.db.set_value('Fund Received', doc_name, 'fund_received_ref_number', int(fund_received_ref_number))
        
#         print(f"DEBUG: Successfully updated Fund Received: {doc_name}")
#         frappe.logger().info(f"Fund Received document updated: {doc_name}")
        
#         # Return the updated document
#         return frappe.get_doc('Fund Received', doc_name)
        
#     except Exception as e:
#         print(f"ERROR updating Fund Received: {str(e)}")
#         frappe.log_error(
#             f"Error updating Fund Received document: {str(e)}", 
#             "Fund Received Update Error"
#         )
#         return None


# def create_fund_budget_breakup_items(fund_received_name, fund_budget_breakup_list):
#     """
#     Creates Fund Budget Breakup Line Items for the Fund Received document.
#     Uses direct DB operations to avoid ORM binding issues in background threads.
    
#     Args:
#         fund_received_name: Name of the parent Fund Received document
#         fund_budget_breakup_list: List of budget breakup items from Kafka message
#     """
#     try:
#         # Child table doctype: Project Received Budget
#         # Parent field: received_amt_breakup
#         child_doctype = 'Project Received Budget'
#         parent_field = 'received_amt_breakup'
        
#         # Clear existing items using direct DB delete
#         frappe.db.delete(child_doctype, {'parent': fund_received_name})
        
#         # Add new items from Kafka message using direct DB insert
#         for idx, item in enumerate(fund_budget_breakup_list, start=1):
#             child_doc = frappe.new_doc(child_doctype)
#             child_doc.parent = fund_received_name
#             child_doc.parenttype = 'Fund Received'
#             child_doc.parentfield = parent_field
#             child_doc.idx = idx
#             # Map accountHeadId to account_head (lookup or direct)
#             child_doc.account_head = item.get('accountHeadId') or item.get('accountHead')
#             child_doc.amount_received = item.get('amount')
#             child_doc.remarks = item.get('remarks')
#             child_doc.db_insert()
        
#         print(f"Created {len(fund_budget_breakup_list)} budget breakup items for {fund_received_name}")
#         frappe.logger().info(
#             f"Created {len(fund_budget_breakup_list)} budget breakup items for {fund_received_name}"
#         )
        
#     except Exception as e:
#         print(f"ERROR creating Fund Budget Breakup items: {str(e)}")
#         frappe.log_error(
#             f"Error creating Fund Budget Breakup items: {str(e)}", 
#             "Fund Budget Breakup Creation Error"
#         )


# def create_transaction_detail_items(fund_received_name, transaction_details_list):
#     """
#     Creates Transaction Detail Line Items for the Fund Received document.
#     Uses direct DB operations to avoid ORM binding issues in background threads.
    
#     Args:
#         fund_received_name: Name of the parent Fund Received document
#         transaction_details_list: List of transaction details from Kafka message
#     """
#     try:
#         # Child table doctype: Project Fund Transaction
#         # Parent field: fund_transactions
#         child_doctype = 'Project Fund Transaction'
#         parent_field = 'fund_transactions'
        
#         # Clear existing items using direct DB delete
#         frappe.db.delete(child_doctype, {'parent': fund_received_name})
        
#         # Add new items from Kafka message using direct DB insert
#         for idx, item in enumerate(transaction_details_list, start=1):
#             # Handle transaction_received_date - can be array [year, month, day] or string
#             date_value = item.get('transactionReceivedDate')
#             if isinstance(date_value, list) and len(date_value) >= 3:
#                 transaction_date = f"{date_value[0]}-{date_value[1]:02d}-{date_value[2]:02d}"
#             elif isinstance(date_value, str):
#                 transaction_date = date_value  # Already a string like "2026-01-07"
#             else:
#                 transaction_date = None
            
#             child_doc = frappe.new_doc(child_doctype)
#             child_doc.parent = fund_received_name
#             child_doc.parenttype = 'Fund Received'
#             child_doc.parentfield = parent_field
#             child_doc.idx = idx
#             # Map to correct field names: transaction_number, transaction_date, amount
#             child_doc.transaction_number = item.get('uniqueTransactionNumber')
#             child_doc.transaction_date = transaction_date
#             child_doc.amount = item.get('transactionAmount')
#             child_doc.db_insert()
        
#         print(f"Created {len(transaction_details_list)} transaction detail items for {fund_received_name}")
#         frappe.logger().info(
#             f"Created {len(transaction_details_list)} transaction detail items for {fund_received_name}"
#         )
        
#     except Exception as e:
#         print(f"ERROR creating Transaction Detail items: {str(e)}")
#         frappe.log_error(
#             f"Error creating Transaction Detail items: {str(e)}", 
#             "Transaction Detail Creation Error"
#         )


# # =============================================================================
# # [ADDED] Import Deposit Slip Consumer Handler from fund_deposits module
# # This uses the DTO layer for validation and field mapping
# # =============================================================================
# from rndopsapp.rndopsapp.fund_deposits import handle_deposit_slip_update


# # Topic to Handler Mapping
# TOPIC_HANDLERS = {
#     TOPIC_ACCOUNTS_FUND_RECEIVED: handle_accounts_fund_received_update,
#     # =============================================================================
#     # [ADDED] Deposit Slip Update Handler
#     # Handles: DEPOSIT_SLIP_UPDATE, DEPOSIT_SLIP_RESEARCH, DEPOSIT_SLIP_CONSULTANCYE
#     # Primary Key: depositSlipRefNumFab (maps to doc.name in Research Consultancy Deposit Slip)
#     # Update Strategy: Direct DB updates for parent, Delete-Insert for child tables
#     # =============================================================================
#     TOPIC_DEPOSIT_SLIP_UPDATE: handle_deposit_slip_update,
# }


# def process_message(topic, message):
#     """
#     Routes a message to its appropriate handler based on topic.
    
#     Args:
#         topic: The Kafka topic the message came from
#         message: The deserialized message payload
    
#     Returns:
#         bool: True if processed successfully, False otherwise
#     """
#     handler = TOPIC_HANDLERS.get(topic)
#     if handler:
#         return handler(message)
#     else:
#         frappe.log_error(
#             f"No handler found for topic: {topic}", 
#             "Kafka Consumer Error"
#         )
#         return False


# def consume_messages(max_messages=None, timeout_ms=1000):
#     """
#     Consumes messages from subscribed Kafka topics.
    
#     Args:
#         max_messages: Maximum number of messages to consume (None for unlimited)
#         timeout_ms: Timeout for poll in milliseconds
        
#     Returns:
#         int: Number of messages successfully processed
#     """
#     consumer = get_consumer()
#     if not consumer:
#         return 0
    
#     # Check for unconsumed offset 0 data before consuming
#     check_unconsumed_offset_zero()
    
#     messages_processed = 0
    
#     try:
#         while max_messages is None or messages_processed < max_messages:
#             # Poll for messages
#             message_batch = consumer.poll(timeout_ms=timeout_ms, max_records=MAX_POLL_RECORDS)
            
#             if not message_batch:
#                 if max_messages is not None:
#                     break  # Exit if no messages and we have a limit
#                 continue
            
#             for topic_partition, messages in message_batch.items():
#                 topic = topic_partition.topic
                
#                 for message in messages:
#                     try:
#                         success = process_message(topic, message.value)
#                         if success:
#                             messages_processed += 1
#                             msg_info = f"Processed message from {topic} | Partition: {message.partition} | Offset: {message.offset}"
#                             print(f"DEBUG: {msg_info}")
#                             frappe.logger().info(msg_info)

#                         else:
#                             frappe.log_error(
#                                 f"Failed to process message from {topic} | "
#                                 f"Partition: {message.partition} | Offset: {message.offset}",
#                                 "Kafka Consumer Processing Error"
#                             )
#                             print(f"DEBUG: Failed to process message from {topic} | Partition: {message.partition} | Offset: {message.offset}")
#                     except Exception as e:
#                         frappe.log_error(
#                             f"Exception processing message: {str(e)}", 
#                             "Kafka Consumer Error"
#                         )
                        
#                     if max_messages is not None and messages_processed >= max_messages:
#                         break
                        
#     except Exception as e:
#         frappe.log_error(f"Error consuming messages: {str(e)}", "Kafka Consumer Error")
    
#     return messages_processed


# def ensure_frappe_site_init():
#     """
#     Ensures Frappe site is properly initialized for the current thread.
#     Required for background threads that need database access.
    
#     Returns:
#         bool: True if site is ready, False otherwise
#     """
#     try:
#         # Check if site is already initialized
#         if frappe.local and hasattr(frappe.local, 'site') and frappe.local.site:
#             # Site is initialized, check DB connection
#             if not frappe.db:
#                 frappe.connect()
#             return True
        
#         # Need to initialize the site
#         import os
        
#         # Get site name from environment or default
#         site_name = os.environ.get('FRAPPE_SITE') or frappe.local.site if hasattr(frappe.local, 'site') else None
        
#         if not site_name:
#             # Try to get from sites directory
#             sites_path = os.environ.get('SITES_PATH') or '.'
#             sites = [d for d in os.listdir(sites_path) 
#                     if os.path.isdir(os.path.join(sites_path, d)) 
#                     and not d.startswith('.') 
#                     and d not in ('assets', 'logs')]
#             if sites:
#                 site_name = sites[0]
#             else:
#                 print("ERROR: Could not determine Frappe site name")
#                 return False
        
#         frappe.init(site=site_name)
#         frappe.connect()
#         print(f"DEBUG: Initialized Frappe site: {site_name}")
#         return True
        
#     except Exception as e:
#         print(f"ERROR: Failed to initialize Frappe site: {str(e)}")
#         return False


# def process_message_with_context(topic, message_value):
#     """
#     Wrapper to process message with proper Frappe context.
#     Ensures database connection is active before processing.
#     """
#     try:
#         # Ensure Frappe site and DB connection are initialized for this thread
#         if not ensure_frappe_site_init():
#             print("ERROR: Failed to initialize Frappe context for message processing")
#             return False
        
#         # Process the message
#         result = process_message(topic, message_value)
        
#         return result
        
#     except Exception as e:
#         print(f"ERROR: Exception in process_message_with_context: {str(e)}")
#         # Try to rollback any partial transaction
#         try:
#             frappe.db.rollback()
#         except:
#             pass
#         return False


# def start_consumer_loop():
#     """
#     Starts an infinite consumer loop in a background thread.
#     Messages are processed as they arrive.
#     """
#     global _stop_consumer
#     _stop_consumer.clear()
    
#     consumer = get_consumer()
#     if not consumer:
#         return False
    
#     # Check for unconsumed offset 0 data on startup
#     # check_unconsumed_offset_zero() # Disabled as we rely on auto_offset_reset with new group
    
#     # Initialize Frappe site for this thread
#     if not ensure_frappe_site_init():
#         print("ERROR: Failed to initialize Frappe site for consumer thread")
#         return False
    
#     frappe.logger().info("Starting Kafka consumer loop...")
#     print("DEBUG: Starting Kafka consumer loop...")
    
#     poll_count = 0
#     try:
#         while not _stop_consumer.is_set():
#             try:
#                 poll_count += 1
#                 assigned = consumer.assignment()
#                 if poll_count <= 5 or poll_count % 10 == 0:
#                     print(f"DEBUG: Poll #{poll_count} | Assigned Partitions: {assigned}")
                
#                 message_batch = consumer.poll(timeout_ms=1000, max_records=MAX_POLL_RECORDS)
                
#                 if message_batch:
#                     print(f"DEBUG: Poll #{poll_count} returned {sum(len(m) for m in message_batch.values())} messages")
#                 elif poll_count <= 5:
#                     print(f"DEBUG: Poll #{poll_count} returned empty")
                
#                 for topic_partition, messages in message_batch.items():
#                     topic = topic_partition.topic
#                     print(f"DEBUG: Received {len(messages)} messages from {topic}")
                    
#                     for message in messages:
#                         if _stop_consumer.is_set():
#                             break
                            
#                         try:
#                             # Use wrapper with Frappe context
#                             process_message_with_context(topic, message.value)
#                         except Exception as e:
#                             print(f"ERROR: Exception in consumer loop: {str(e)}")
#                             frappe.log_error(
#                                 f"Exception in consumer loop: {str(e)}", 
#                                 "Kafka Consumer Loop Error"
#                             )
                            
#             except Exception as e:
#                 if not _stop_consumer.is_set():
#                     print(f"ERROR: Consumer loop error: {str(e)}")
#                     frappe.log_error(f"Consumer loop error: {str(e)}", "Kafka Consumer Error")
#                     time.sleep(RETRY_DELAY_SECONDS)
                    
#     except Exception as e:
#         print(f"ERROR: Consumer loop terminated: {str(e)}")
#         frappe.log_error(f"Consumer loop terminated: {str(e)}", "Kafka Consumer Error")
#     finally:
#         close_consumer()
        
#     frappe.logger().info("Kafka consumer loop stopped")
#     print("DEBUG: Kafka consumer loop stopped")
#     return True


# def start_consumer_thread():
#     """
#     Starts the consumer loop in a background thread.
    
#     Returns:
#         bool: True if thread started successfully, False otherwise
#     """
#     global _consumer_thread
    
#     if _consumer_thread is not None and _consumer_thread.is_alive():
#         frappe.logger().warning("Consumer thread is already running")
#         return False
    
#     _consumer_thread = threading.Thread(
#         target=start_consumer_loop,
#         name="KafkaConsumerThread",
#         daemon=True
#     )
#     _consumer_thread.start()
#     frappe.logger().info("Kafka consumer thread started")
#     print("DEBUG: Kafka consumer thread started")
#     return True


# def stop_consumer_thread():
#     """
#     Stops the consumer loop and thread gracefully.
#     """
#     global _consumer_thread, _stop_consumer
    
#     _stop_consumer.set()
    
#     if _consumer_thread is not None:
#         _consumer_thread.join(timeout=10)
#         if _consumer_thread.is_alive():
#             frappe.logger().warning("Consumer thread did not stop gracefully")
#         else:
#             frappe.logger().info("Consumer thread stopped")
#         _consumer_thread = None
        
#     close_consumer()


# def get_consumer_status():
#     """
#     Returns the current status of the Kafka consumer.
    
#     Returns:
#         dict: Status information including running state and subscribed topics
#     """
#     global _consumer, _consumer_thread
    
#     return {
#         "kafka_available": KAFKA_AVAILABLE,
#         "consumer_connected": _consumer is not None,
#         "consumer_thread_running": _consumer_thread is not None and _consumer_thread.is_alive(),
#         "subscribed_topics": CONSUME_TOPICS,
#         "consumer_group_id": CONSUMER_GROUP_ID,
#         "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS
#     }


# # ==========================================
# # Frappe Commands / Hooks
# # ==========================================

# @frappe.whitelist()
# def start_kafka_consumer():
#     """
#     Frappe whitelisted method to start the Kafka consumer.
#     Can be called from the UI or via API.
#     """
#     try:
#         success = start_consumer_thread()
#         if success:
#             return {"status": "success", "message": "Kafka consumer started"}
#         else:
#             return {"status": "warning", "message": "Consumer thread already running"}
#     except Exception as e:
#         return {"status": "error", "message": str(e)}


# @frappe.whitelist()
# def stop_kafka_consumer():
#     """
#     Frappe whitelisted method to stop the Kafka consumer.
#     """
#     try:
#         stop_consumer_thread()
#         return {"status": "success", "message": "Kafka consumer stopped"}
#     except Exception as e:
#         return {"status": "error", "message": str(e)}


# @frappe.whitelist()
# def get_kafka_consumer_status():
#     """
#     Frappe whitelisted method to get consumer status.
#     """
#     return get_consumer_status()


# @frappe.whitelist()
# def consume_kafka_messages(max_messages=10):
#     """
#     Frappe whitelisted method to consume a specific number of messages.
#     Useful for manual/batch processing.
    
#     Args:
#         max_messages: Maximum number of messages to consume
        
#     Returns:
#         dict: Result with number of messages processed
#     """
#     try:
#         max_messages = int(max_messages)
#         processed = consume_messages(max_messages=max_messages, timeout_ms=5000)
#         return {
#             "status": "success", 
#             "messages_processed": processed
#         }
#     except Exception as e:
#         return {"status": "error", "message": str(e)}


# @frappe.whitelist()
# def reset_consumer_offset_to_beginning():
#     """
#     Frappe whitelisted method to reset consumer offset to beginning (offset 0).
#     Useful for reprocessing all messages from the start.

#     [UPDATED] Now resets offsets for ALL topics in CONSUME_TOPICS

#     Returns:
#         dict: Result with status
#     """
#     try:
#         # Close global consumer if open to avoid conflicts
#         close_consumer()

#         from kafka import KafkaConsumer, TopicPartition

#         # Create a fresh consumer WITHOUT subscribing (no topics in init)
#         # Using the same GROUP ID to reset its offsets.
#         consumer = KafkaConsumer(
#             bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
#             group_id=CONSUMER_GROUP_ID,
#             value_deserializer=lambda v: json.loads(v.decode('utf-8')),
#             auto_offset_reset='earliest',
#             enable_auto_commit=False # We will commit manually
#         )

#         # =============================================================================
#         # [UPDATED] Get partitions for ALL topics in CONSUME_TOPICS
#         # =============================================================================
#         all_tps = []
#         topics_found = []

#         for topic in CONSUME_TOPICS:
#             partition_ids = consumer.partitions_for_topic(topic)
#             if partition_ids:
#                 tps = [TopicPartition(topic, p) for p in partition_ids]
#                 all_tps.extend(tps)
#                 topics_found.append(topic)
#                 frappe.logger().info(f"Found {len(partition_ids)} partitions for topic {topic}")
#             else:
#                 frappe.logger().warning(f"No partitions found for topic {topic}")

#         if not all_tps:
#             consumer.close()
#             return {"status": "error", "message": f"No partitions found for any topic in {CONSUME_TOPICS}"}

#         # Assign all partitions
#         consumer.assign(all_tps)
#         frappe.logger().info(f"Assigned {len(all_tps)} partitions across {len(topics_found)} topics")

#         # Seek to beginning
#         consumer.seek_to_beginning()

#         # Verify position
#         for tp in all_tps:
#             pos = consumer.position(tp)
#             frappe.logger().info(f"Topic {tp.topic} Partition {tp.partition} reset to offset {pos}")

#         # Commit
#         consumer.commit()
#         frappe.logger().info("Offsets committed.")

#         consumer.close()

#         return {
#             "status": "success",
#             "message": f"Offsets reset to beginning for {len(all_tps)} partitions across {len(topics_found)} topics",
#             "topics": topics_found,
#             "total_partitions": len(all_tps)
#         }
#     except Exception as e:
#         frappe.log_error(f"Error resetting consumer offset: {str(e)}", "Offset Reset Error")
#         return {"status": "error", "message": str(e)}



import frappe
import json
import time
import threading
from datetime import datetime
from frappe import _
import logging # [ADDED]

try:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False


# --- LOGGING SETUP [ADDED] ---
# Setup for error.log
error_logger = logging.getLogger('kafka_consumer_error')
error_logger.setLevel(logging.ERROR)
# Check if handlers already exist to avoid duplicate logs if module is reloaded
if not error_logger.handlers:
    error_handler = logging.FileHandler('error.log')
    error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    error_logger.addHandler(error_handler)

# Setup for kafka.log
kafka_logger = logging.getLogger('kafka_consumer_activity')
kafka_logger.setLevel(logging.INFO)
if not kafka_logger.handlers:
    kafka_handler = logging.FileHandler('kafka.log')
    kafka_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    kafka_logger.addHandler(kafka_handler)
# -----------------------------


# --- CONFIGURATION ---
# Import Kafka configuration from centralized config
from rndopsapp.config import KAFKA_BOOTSTRAP_SERVERS

# Consumer Group ID
CONSUMER_GROUP_ID = 'rndopsapp-consumer-group-v2'

# Topic to consume
TOPIC_ACCOUNTS_FUND_RECEIVED = 'accounts-fundreceived-update'

# =============================================================================
# [ADDED] Deposit Slip Update Topic - Receives updates from colleague's system
# =============================================================================
TOPIC_DEPOSIT_SLIP_UPDATE = 'accounts-depositslip-update'

# All Topics to Consume
CONSUME_TOPICS = [
    TOPIC_ACCOUNTS_FUND_RECEIVED,
    TOPIC_DEPOSIT_SLIP_UPDATE,  # [ADDED] Deposit Slip Update Topic
]

# Consumer Configuration
AUTO_OFFSET_RESET = 'earliest'  # Start from earliest if no committed offset
ENABLE_AUTO_COMMIT = True
AUTO_COMMIT_INTERVAL_MS = 5000  # Commit offsets every 5 seconds
SESSION_TIMEOUT_MS = 30000
HEARTBEAT_INTERVAL_MS = 10000
MAX_POLL_RECORDS = 100
MAX_POLL_INTERVAL_MS = 300000

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1

# Singleton Consumer Instance
_consumer = None
_consumer_thread = None
_stop_consumer = threading.Event()


def get_consumer():
    """
    Returns a singleton KafkaConsumer instance.
    Reuses the same connection for all message consumption.
    """
    global _consumer

    if not KAFKA_AVAILABLE:
        print("ERROR: kafka-python library not installed")
        frappe.log_error("kafka-python library not installed", "Kafka Consumer Error")
        error_logger.error("kafka-python library not installed") # [ADDED]
        return None

    if _consumer is not None:
        return _consumer

    try:
        from kafka import TopicPartition
        
        # Create consumer WITHOUT group_id (manual assign doesn't need group coordination)
        _consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            # group_id=CONSUMER_GROUP_ID,  # Removed - conflicts with assign()
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            auto_offset_reset=AUTO_OFFSET_RESET,
            enable_auto_commit=False,  # No group, so no auto-commit
            session_timeout_ms=SESSION_TIMEOUT_MS,
            heartbeat_interval_ms=HEARTBEAT_INTERVAL_MS,
            max_poll_records=MAX_POLL_RECORDS,
            max_poll_interval_ms=MAX_POLL_INTERVAL_MS
        )
        
        # Manually assign partitions (bypasses group coordinator)
        # =============================================================================
        # [UPDATED] Now assigns partitions for ALL topics in CONSUME_TOPICS
        # =============================================================================
        all_topic_partitions = []

        for topic in CONSUME_TOPICS:
            print(f"DEBUG: Getting partitions for topic: {topic}")
            kafka_logger.info(f"Getting partitions for topic: {topic}") # [ADDED]
            partitions = _consumer.partitions_for_topic(topic)

            if partitions:
                tps = [TopicPartition(topic, p) for p in partitions]
                all_topic_partitions.extend(tps)
                print(f"DEBUG: Found {len(partitions)} partitions for topic {topic}")
                kafka_logger.info(f"Found {len(partitions)} partitions for topic {topic}") # [ADDED]
            else:
                print(f"WARNING: No partitions found for topic {topic} (topic may not exist yet)")
                kafka_logger.warning(f"No partitions found for topic {topic}") # [ADDED]

        if all_topic_partitions:
            _consumer.assign(all_topic_partitions)
            print(f"DEBUG: Manually assigned {len(all_topic_partitions)} partitions: {all_topic_partitions}")
            kafka_logger.info(f"Manually assigned {len(all_topic_partitions)} partitions") # [ADDED]

            # Seek to beginning for fresh start
            _consumer.seek_to_beginning()
            print(f"DEBUG: Seeked to beginning of all partitions")
            kafka_logger.info("Seeked to beginning of all partitions") # [ADDED]

            # Verify positions
            for tp in all_topic_partitions:
                pos = _consumer.position(tp)
                print(f"DEBUG: Topic {tp.topic} Partition {tp.partition} position after seek: {pos}")
        else:
            print(f"ERROR: No partitions found for any topic in {CONSUME_TOPICS}")
            error_logger.error(f"No partitions found for any topic in {CONSUME_TOPICS}") # [ADDED]
        
        print(f"DEBUG: Kafka Consumer connected to topics: {CONSUME_TOPICS}")
        kafka_logger.info(f"Kafka Consumer connected to topics: {CONSUME_TOPICS}") # [ADDED]
        return _consumer
    except Exception as e:
        print(f"ERROR: Failed to connect Kafka Consumer: {str(e)}")
        frappe.log_error(f"Failed to connect Kafka Consumer: {str(e)}", "Kafka Consumer Connection Error")
        error_logger.error(f"Failed to connect Kafka Consumer: {str(e)}") # [ADDED]
        return None


def close_consumer():
    """
    Closes the singleton consumer instance.
    """
    global _consumer
    if _consumer is not None:
        try:
            _consumer.close()
            print("DEBUG: Kafka Consumer closed successfully")
            frappe.logger().info("Kafka Consumer closed successfully")
            kafka_logger.info("Kafka Consumer closed successfully") # [ADDED]
        except Exception as e:
            print(f"ERROR: Error closing Kafka Consumer: {str(e)}")
            frappe.log_error(f"Error closing Kafka Consumer: {str(e)}", "Kafka Consumer Error")
            error_logger.error(f"Error closing Kafka Consumer: {str(e)}") # [ADDED]
        finally:
            _consumer = None


def check_unconsumed_offset_zero():
    """
    Checks for unconsumed messages at offset 0 in the topic.
    Resets offset to 0 if needed to consume from beginning.

    [UPDATED] Now checks ALL topics in CONSUME_TOPICS
    """
    try:
        consumer = get_consumer()
        if not consumer:
            frappe.logger().warning("Consumer not available for offset check")
            kafka_logger.warning("Consumer not available for offset check") # [ADDED]
            return False

        from kafka import TopicPartition

        # =============================================================================
        # [UPDATED] Check offset for ALL topics in CONSUME_TOPICS
        # =============================================================================
        for topic in CONSUME_TOPICS:
            partitions = consumer.partitions_for_topic(topic)
            if not partitions:
                frappe.logger().warning(f"No partitions found for topic: {topic}")
                kafka_logger.warning(f"No partitions found for topic: {topic}") # [ADDED]
                continue

            frappe.logger().info(f"Found partitions for {topic}: {partitions}")

            # Check offset and committed offset for each partition
            for partition in partitions:
                tp = TopicPartition(topic, partition)

                # Get committed offset
                committed_offset = consumer.committed(tp)
                frappe.logger().info(f"Topic {topic} Partition {partition} - Committed offset: {committed_offset}")
                kafka_logger.info(f"Topic {topic} Partition {partition} - Committed offset: {committed_offset}") # [ADDED]

                # If no committed offset (None), it means we haven't consumed any messages
                if committed_offset is None:
                    frappe.logger().info(
                        f"No committed offset for {topic} partition {partition}. "
                        f"Will consume from offset 0 (earliest)"
                    )
                    # Seek to beginning
                    consumer.seek(tp, 0)
                    frappe.logger().info(f"Seek to offset 0 for {topic} partition {partition}")
                    kafka_logger.info(f"Seek to offset 0 for {topic} partition {partition}") # [ADDED]

        return True

    except Exception as e:
        frappe.log_error(
            f"Error checking unconsumed offset 0: {str(e)}",
            "Offset Check Error"
        )
        error_logger.error(f"Error checking unconsumed offset 0: {str(e)}") # [ADDED]
        return False


# ==========================================
# Message Handlers
# ==========================================

def handle_accounts_fund_received_update(message):
    """
    Handler for accounts-fundreceived-update topic.
    Processes incoming fund received update messages and creates/updates Frappe documents.
    """
    try:
        data = message.get('data', {})
        schema_version = message.get('schemaVersion', '1.0')
        event_type = message.get('eventType', 'UNKNOWN')
        timestamp = message.get('timestamp')
        
        fund_received_ref_number = data.get('fundReceivedRefNumber')
        fund_received_ref_number_fap = data.get('fundReceivedRefNumberFap')
        sanction_letter_no = data.get('sanctionLetterNo')
        project_number = data.get('projectNumber')
        amount_received = data.get('amountReceived')
        iitg_account_number = data.get('iitgAccountNumber')
        deposit_slip_status = data.get('depositSlipStatus')
        fund_received_status = data.get('fundReceivedStatus')
        fund_budget_breakup_list = data.get('fundBudgetBreakupList', [])
        transaction_details_list = data.get('transactionDetailsList', [])
        
        print(f"Consumed Data: {json.dumps(data, indent=2)}")
        frappe.logger().info(
            f"Processing Accounts Fund Received Update: Ref# {fund_received_ref_number} | "
            f"Project: {project_number} | Amount: {amount_received} | "
            f"Status: {fund_received_status} | Event: {event_type}"
        )
        kafka_logger.info(f"Processing Accounts Fund Received Update: Ref# {fund_received_ref_number}") # [ADDED]
        
        # Update Fund Received document (Update Only)
        fund_received_doc = update_fund_received(
            fund_received_ref_number=fund_received_ref_number,
            fund_received_ref_number_fap=fund_received_ref_number_fap,
            sanction_letter_no=sanction_letter_no,
            project_number=project_number,
            amount_received=amount_received,
            iitg_account_number=iitg_account_number,
            deposit_slip_status=deposit_slip_status,
            fund_received_status=fund_received_status,
            timestamp=timestamp
        )
        
        if fund_received_doc:
            # Commit changes from update_fund_received before modifying child tables
            frappe.db.commit()
            
            # Process Fund Budget Breakup List
            if fund_budget_breakup_list:
                create_fund_budget_breakup_items(
                    fund_received_doc.name,
                    fund_budget_breakup_list
                )
            
            # Process Transaction Details List
            if transaction_details_list:
                create_transaction_detail_items(
                    fund_received_doc.name,
                    transaction_details_list
                )
            
            frappe.db.commit()
            print(f"Successfully processed and updated: {fund_received_doc.name}")
            kafka_logger.info(f"Successfully processed and updated: {fund_received_doc.name}") # [ADDED]
            return True
        else:
            print(f"Skipping: Fund Received document {fund_received_ref_number} not found.")
            kafka_logger.info(f"Skipping: Fund Received document {fund_received_ref_number} not found.") # [ADDED]
            return True # Return True to commit offset even if doc not found

        
    except Exception as e:
        frappe.log_error(
            f"Error processing accounts fund received update message: {str(e)}", 
            "Kafka Consumer Handler Error"
        )
        error_logger.error(f"Error processing accounts fund received update message: {str(e)}") # [ADDED]
        return False


def update_fund_received(**kwargs):
    """
    Updates an existing Fund Received document in Frappe.
    
    Args:
        fund_received_ref_number: Reference number (assumed to be doc ID/Name)
        sanction_letter_no: Sanction letter number
        project_number: Project number
        amount_received: Amount received
        iitg_account_number: IITG account number
        deposit_slip_status: Status of deposit slip
        fund_received_status: Status of fund received
        timestamp: Timestamp of the event
        
    Returns:
        Fund Received document or None if not found/error
    """
    try:
        fund_received_ref_number = kwargs.get('fund_received_ref_number')
        fund_received_ref_number_fap = kwargs.get('fund_received_ref_number_fap')
        
        # Check if document exists by Name (Ref Number FAP) - Primary lookup
        if fund_received_ref_number_fap and frappe.db.exists('Fund Received', fund_received_ref_number_fap):
             fund_received = frappe.get_doc('Fund Received', fund_received_ref_number_fap)
        # Fallback: Check if document exists by Name (Ref Number)
        elif frappe.db.exists('Fund Received', fund_received_ref_number):
             fund_received = frappe.get_doc('Fund Received', fund_received_ref_number)
        else:
             # Fallback: Try to find by sanction letter and project
             sanction_letter_no = kwargs.get('sanction_letter_no')
             project_number = kwargs.get('project_number')
             
             filters = {
                 'sanctioned_letter_no': sanction_letter_no,
                 'prjreg_title': project_number
             }
             found_name = frappe.db.get_value('Fund Received', filters, 'name')
             
             if found_name:
                 print(f"Found Fund Received by fallback lookup: {found_name}")
                 kafka_logger.info(f"Found Fund Received by fallback lookup: {found_name}") # [ADDED]
                 fund_received = frappe.get_doc('Fund Received', found_name)
             else:
                 print(f"Fund Received document not found: {fund_received_ref_number} or via filters {filters}")
                 frappe.logger().warning(f"Fund Received document not found: {fund_received_ref_number}")
                 kafka_logger.warning(f"Fund Received document not found: {fund_received_ref_number}") # [ADDED]
                 return None

        print(f"DEBUG: Updating Fund Received: {fund_received.name}")
        frappe.logger().info(f"Updating existing Fund Received: {fund_received.name}")
        
        # Use frappe.db.set_value for direct DB updates (bypasses controller validations)
        # This allows updating submitted documents
        doc_name = fund_received.name
        
        # Map sanction_letter_no
        if kwargs.get('sanction_letter_no'):
            frappe.db.set_value('Fund Received', doc_name, 'sanctioned_letter_no', kwargs.get('sanction_letter_no'))
        
        # Map project_number to prjreg_title (Link Field)
        if kwargs.get('project_number'):
            frappe.db.set_value('Fund Received', doc_name, 'prjreg_title', kwargs.get('project_number'))
        
        # Map amountReceived -> fund_received_amt
        if kwargs.get('amount_received') is not None:
            frappe.db.set_value('Fund Received', doc_name, 'fund_received_amt', kwargs.get('amount_received'))
        
        # Map iitgAccountNumber -> bank_account
        if kwargs.get('iitg_account_number'):
            frappe.db.set_value('Fund Received', doc_name, 'bank_account', kwargs.get('iitg_account_number'))
        
        # Map fundReceivedStatus -> workflow_state
        # Guard: never move the document backward in the workflow.
        # APPROVED from Kafka maps to "Pending Misc. Staff Approval(Deposit Slip Pending)"
        # which is BEHIND "Pending HoS Approval" or "Approved" — skip if already ahead.
        # Source of truth: fund_received_with_kafka workflow (verified from DB).
        _STATE_PRIORITY = {
            'Draft':                                                 0,
            'Pending Misc. Staff Approval':                          1,
            'PENDING_APPROVAL':                                      2,
            'Pending Misc. Staff Approval(Deposit Slip Pending)':    3,
            'Pending HoS Approval':                                  4,
            'Approved':                                              5,
            'Fund Received':                                         6,
        }
        fund_received_status = kwargs.get('fund_received_status')
        if fund_received_status:
            status_upper = fund_received_status.upper()
            if status_upper == 'APPROVED':
                new_status = 'Pending Misc. Staff Approval(Deposit Slip Pending)'
            elif status_upper == 'PENDING_APPROVAL':
                # Must use the exact state name, not title-cased 'Pending_Approval'
                new_status = 'PENDING_APPROVAL'
            else:
                new_status = fund_received_status.title()

            current_status = frappe.db.get_value('Fund Received', doc_name, 'workflow_state') or ''
            current_priority = _STATE_PRIORITY.get(current_status, 0)
            new_priority = _STATE_PRIORITY.get(new_status, 0)
            if new_priority >= current_priority:
                frappe.db.set_value('Fund Received', doc_name, 'workflow_state', new_status)
            else:
                frappe.logger().warning(
                    f"[kafka_consumer] Skipped backward state change for {doc_name}: "
                    f"'{current_status}' (priority {current_priority}) "
                    f"→ '{new_status}' (priority {new_priority}) ignored."
                )
        
        # Map fundReceivedRefNumber -> fund_received_ref_number (integer field)
        if fund_received_ref_number is not None:
            frappe.db.set_value('Fund Received', doc_name, 'fund_received_ref_number', int(fund_received_ref_number))
        
        print(f"DEBUG: Successfully updated Fund Received: {doc_name}")
        frappe.logger().info(f"Fund Received document updated: {doc_name}")
        kafka_logger.info(f"Fund Received document updated: {doc_name}") # [ADDED]
        
        # Return the updated document
        return frappe.get_doc('Fund Received', doc_name)
        
    except Exception as e:
        print(f"ERROR updating Fund Received: {str(e)}")
        frappe.log_error(
            f"Error updating Fund Received document: {str(e)}", 
            "Fund Received Update Error"
        )
        error_logger.error(f"Error updating Fund Received document: {str(e)}") # [ADDED]
        return None


def create_fund_budget_breakup_items(fund_received_name, fund_budget_breakup_list):
    """
    Creates Fund Budget Breakup Line Items for the Fund Received document.
    Uses direct DB operations to avoid ORM binding issues in background threads.
    
    Args:
        fund_received_name: Name of the parent Fund Received document
        fund_budget_breakup_list: List of budget breakup items from Kafka message
    """
    try:
        # Child table doctype: Project Received Budget
        # Parent field: received_amt_breakup
        child_doctype = 'Project Received Budget'
        parent_field = 'received_amt_breakup'
        
        # Clear existing items using direct DB delete
        frappe.db.delete(child_doctype, {'parent': fund_received_name})
        
        # Add new items from Kafka message using direct DB insert
        for idx, item in enumerate(fund_budget_breakup_list, start=1):
            child_doc = frappe.new_doc(child_doctype)
            child_doc.parent = fund_received_name
            child_doc.parenttype = 'Fund Received'
            child_doc.parentfield = parent_field
            child_doc.idx = idx
            # Map accountHeadId to account_head (lookup or direct)
            child_doc.account_head = item.get('accountHeadId') or item.get('accountHead')
            child_doc.amount_received = item.get('amount')
            child_doc.remarks = item.get('remarks')
            child_doc.db_insert()
        
        print(f"Created {len(fund_budget_breakup_list)} budget breakup items for {fund_received_name}")
        frappe.logger().info(
            f"Created {len(fund_budget_breakup_list)} budget breakup items for {fund_received_name}"
        )
        
    except Exception as e:
        print(f"ERROR creating Fund Budget Breakup items: {str(e)}")
        frappe.log_error(
            f"Error creating Fund Budget Breakup items: {str(e)}", 
            "Fund Budget Breakup Creation Error"
        )
        error_logger.error(f"Error creating Fund Budget Breakup items: {str(e)}") # [ADDED]


def create_transaction_detail_items(fund_received_name, transaction_details_list):
    """
    Creates Transaction Detail Line Items for the Fund Received document.
    Uses direct DB operations to avoid ORM binding issues in background threads.
    
    Args:
        fund_received_name: Name of the parent Fund Received document
        transaction_details_list: List of transaction details from Kafka message
    """
    try:
        # Child table doctype: Project Fund Transaction
        # Parent field: fund_transactions
        child_doctype = 'Project Fund Transaction'
        parent_field = 'fund_transactions'
        
        # Clear existing items using direct DB delete
        frappe.db.delete(child_doctype, {'parent': fund_received_name})
        
        # Add new items from Kafka message using direct DB insert
        for idx, item in enumerate(transaction_details_list, start=1):
            # Handle transaction_received_date - can be array [year, month, day] or string
            date_value = item.get('transactionReceivedDate')
            if isinstance(date_value, list) and len(date_value) >= 3:
                transaction_date = f"{date_value[0]}-{date_value[1]:02d}-{date_value[2]:02d}"
            elif isinstance(date_value, str):
                transaction_date = date_value  # Already a string like "2026-01-07"
            else:
                transaction_date = None
            
            child_doc = frappe.new_doc(child_doctype)
            child_doc.parent = fund_received_name
            child_doc.parenttype = 'Fund Received'
            child_doc.parentfield = parent_field
            child_doc.idx = idx
            # Map to correct field names: transaction_number, transaction_date, amount
            child_doc.transaction_number = item.get('uniqueTransactionNumber')
            child_doc.transaction_date = transaction_date
            child_doc.amount = item.get('transactionAmount')
            child_doc.db_insert()
        
        print(f"Created {len(transaction_details_list)} transaction detail items for {fund_received_name}")
        frappe.logger().info(
            f"Created {len(transaction_details_list)} transaction detail items for {fund_received_name}"
        )
        
    except Exception as e:
        print(f"ERROR creating Transaction Detail items: {str(e)}")
        frappe.log_error(
            f"Error creating Transaction Detail items: {str(e)}", 
            "Transaction Detail Creation Error"
        )
        error_logger.error(f"Error creating Transaction Detail items: {str(e)}") # [ADDED]


# =============================================================================
# [ADDED] Import Deposit Slip Consumer Handler from fund_deposits module
# This uses the DTO layer for validation and field mapping
# =============================================================================
from rndopsapp.rndopsapp.fund_deposits import handle_deposit_slip_update


# Topic to Handler Mapping
TOPIC_HANDLERS = {
    TOPIC_ACCOUNTS_FUND_RECEIVED: handle_accounts_fund_received_update,
    # =============================================================================
    # [ADDED] Deposit Slip Update Handler
    # Handles: DEPOSIT_SLIP_UPDATE, DEPOSIT_SLIP_RESEARCH, DEPOSIT_SLIP_CONSULTANCYE
    # Primary Key: depositSlipRefNumFab (maps to doc.name in Research Consultancy Deposit Slip)
    # Update Strategy: Direct DB updates for parent, Delete-Insert for child tables
    # =============================================================================
    TOPIC_DEPOSIT_SLIP_UPDATE: handle_deposit_slip_update,
}


def process_message(topic, message):
    """
    Routes a message to its appropriate handler based on topic.
    
    Args:
        topic: The Kafka topic the message came from
        message: The deserialized message payload
    
    Returns:
        bool: True if processed successfully, False otherwise
    """
    handler = TOPIC_HANDLERS.get(topic)
    if handler:
        return handler(message)
    else:
        frappe.log_error(
            f"No handler found for topic: {topic}", 
            "Kafka Consumer Error"
        )
        error_logger.error(f"No handler found for topic: {topic}") # [ADDED]
        return False


def consume_messages(max_messages=None, timeout_ms=1000):
    """
    Consumes messages from subscribed Kafka topics.
    
    Args:
        max_messages: Maximum number of messages to consume (None for unlimited)
        timeout_ms: Timeout for poll in milliseconds
        
    Returns:
        int: Number of messages successfully processed
    """
    consumer = get_consumer()
    if not consumer:
        return 0
    
    # Check for unconsumed offset 0 data before consuming
    check_unconsumed_offset_zero()
    
    messages_processed = 0
    
    try:
        while max_messages is None or messages_processed < max_messages:
            # Poll for messages
            message_batch = consumer.poll(timeout_ms=timeout_ms, max_records=MAX_POLL_RECORDS)
            
            if not message_batch:
                if max_messages is not None:
                    break  # Exit if no messages and we have a limit
                continue
            
            for topic_partition, messages in message_batch.items():
                topic = topic_partition.topic
                
                for message in messages:
                    try:
                        success = process_message(topic, message.value)
                        if success:
                            messages_processed += 1
                            msg_info = f"Processed message from {topic} | Partition: {message.partition} | Offset: {message.offset}"
                            print(f"DEBUG: {msg_info}")
                            frappe.logger().info(msg_info)
                            kafka_logger.info(msg_info) # [ADDED]

                        else:
                            frappe.log_error(
                                f"Failed to process message from {topic} | "
                                f"Partition: {message.partition} | Offset: {message.offset}",
                                "Kafka Consumer Processing Error"
                            )
                            print(f"DEBUG: Failed to process message from {topic} | Partition: {message.partition} | Offset: {message.offset}")
                            error_logger.error(f"Failed to process message from {topic} | Partition: {message.partition} | Offset: {message.offset}") # [ADDED]
                    except Exception as e:
                        frappe.log_error(
                            f"Exception processing message: {str(e)}", 
                            "Kafka Consumer Error"
                        )
                        error_logger.error(f"Exception processing message: {str(e)}") # [ADDED]
                        
                    if max_messages is not None and messages_processed >= max_messages:
                        break
                        
    except Exception as e:
        frappe.log_error(f"Error consuming messages: {str(e)}", "Kafka Consumer Error")
        error_logger.error(f"Error consuming messages: {str(e)}") # [ADDED]
    
    return messages_processed


def ensure_frappe_site_init():
    """
    Ensures Frappe site is properly initialized for the current thread.
    Required for background threads that need database access.
    
    Returns:
        bool: True if site is ready, False otherwise
    """
    try:
        # Check if site is already initialized
        if frappe.local and hasattr(frappe.local, 'site') and frappe.local.site:
            # Site is initialized, check DB connection
            if not frappe.db:
                frappe.connect()
            return True
        
        # Need to initialize the site
        import os
        
        # Get site name from environment or default
        site_name = os.environ.get('FRAPPE_SITE') or frappe.local.site if hasattr(frappe.local, 'site') else None
        
        if not site_name:
            # Try to get from sites directory
            sites_path = os.environ.get('SITES_PATH') or '.'
            sites = [d for d in os.listdir(sites_path) 
                    if os.path.isdir(os.path.join(sites_path, d)) 
                    and not d.startswith('.') 
                    and d not in ('assets', 'logs')]
            if sites:
                site_name = sites[0]
            else:
                print("ERROR: Could not determine Frappe site name")
                error_logger.error("Could not determine Frappe site name") # [ADDED]
                return False
        
        frappe.init(site=site_name)
        frappe.connect()
        print(f"DEBUG: Initialized Frappe site: {site_name}")
        kafka_logger.info(f"Initialized Frappe site: {site_name}") # [ADDED]
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to initialize Frappe site: {str(e)}")
        error_logger.error(f"Failed to initialize Frappe site: {str(e)}") # [ADDED]
        return False


def process_message_with_context(topic, message_value):
    """
    Wrapper to process message with proper Frappe context.
    Ensures database connection is active before processing.
    """
    try:
        # Ensure Frappe site and DB connection are initialized for this thread
        if not ensure_frappe_site_init():
            print("ERROR: Failed to initialize Frappe context for message processing")
            error_logger.error("Failed to initialize Frappe context for message processing") # [ADDED]
            return False
        
        # Process the message
        result = process_message(topic, message_value)
        
        return result
        
    except Exception as e:
        print(f"ERROR: Exception in process_message_with_context: {str(e)}")
        error_logger.error(f"Exception in process_message_with_context: {str(e)}") # [ADDED]
        # Try to rollback any partial transaction
        try:
            frappe.db.rollback()
        except:
            pass
        return False


def start_consumer_loop():
    """
    Starts an infinite consumer loop in a background thread.
    Messages are processed as they arrive.
    """
    global _stop_consumer
    _stop_consumer.clear()
    
    consumer = get_consumer()
    if not consumer:
        return False
    
    # Check for unconsumed offset 0 data on startup
    # check_unconsumed_offset_zero() # Disabled as we rely on auto_offset_reset with new group
    
    # Initialize Frappe site for this thread
    if not ensure_frappe_site_init():
        print("ERROR: Failed to initialize Frappe site for consumer thread")
        error_logger.error("Failed to initialize Frappe site for consumer thread") # [ADDED]
        return False
    
    frappe.logger().info("Starting Kafka consumer loop...")
    print("DEBUG: Starting Kafka consumer loop...")
    kafka_logger.info("Starting Kafka consumer loop...") # [ADDED]
    
    poll_count = 0
    try:
        while not _stop_consumer.is_set():
            try:
                poll_count += 1
                assigned = consumer.assignment()
                if poll_count <= 5 or poll_count % 10 == 0:
                    print(f"DEBUG: Poll #{poll_count} | Assigned Partitions: {assigned}")
                
                message_batch = consumer.poll(timeout_ms=1000, max_records=MAX_POLL_RECORDS)
                
                if message_batch:
                    print(f"DEBUG: Poll #{poll_count} returned {sum(len(m) for m in message_batch.values())} messages")
                elif poll_count <= 5:
                    print(f"DEBUG: Poll #{poll_count} returned empty")
                
                for topic_partition, messages in message_batch.items():
                    topic = topic_partition.topic
                    print(f"DEBUG: Received {len(messages)} messages from {topic}")
                    kafka_logger.info(f"Received {len(messages)} messages from {topic}") # [ADDED]
                    
                    for message in messages:
                        if _stop_consumer.is_set():
                            break
                            
                        try:
                            # Use wrapper with Frappe context
                            process_message_with_context(topic, message.value)
                        except Exception as e:
                            print(f"ERROR: Exception in consumer loop: {str(e)}")
                            frappe.log_error(
                                f"Exception in consumer loop: {str(e)}", 
                                "Kafka Consumer Loop Error"
                            )
                            error_logger.error(f"Exception in consumer loop: {str(e)}") # [ADDED]
                            
            except Exception as e:
                if not _stop_consumer.is_set():
                    print(f"ERROR: Consumer loop error: {str(e)}")
                    frappe.log_error(f"Consumer loop error: {str(e)}", "Kafka Consumer Error")
                    error_logger.error(f"Consumer loop error: {str(e)}") # [ADDED]
                    time.sleep(RETRY_DELAY_SECONDS)
                    
    except Exception as e:
        print(f"ERROR: Consumer loop terminated: {str(e)}")
        frappe.log_error(f"Consumer loop terminated: {str(e)}", "Kafka Consumer Error")
        error_logger.error(f"Consumer loop terminated: {str(e)}") # [ADDED]
    finally:
        close_consumer()
        
    frappe.logger().info("Kafka consumer loop stopped")
    print("DEBUG: Kafka consumer loop stopped")
    kafka_logger.info("Kafka consumer loop stopped") # [ADDED]
    return True


def start_consumer_thread():
    """
    Starts the consumer loop in a background thread.
    
    Returns:
        bool: True if thread started successfully, False otherwise
    """
    global _consumer_thread
    
    if _consumer_thread is not None and _consumer_thread.is_alive():
        frappe.logger().warning("Consumer thread is already running")
        return False
    
    _consumer_thread = threading.Thread(
        target=start_consumer_loop,
        name="KafkaConsumerThread",
        daemon=True
    )
    _consumer_thread.start()
    frappe.logger().info("Kafka consumer thread started")
    print("DEBUG: Kafka consumer thread started")
    kafka_logger.info("Kafka consumer thread started") # [ADDED]
    return True


def stop_consumer_thread():
    """
    Stops the consumer loop and thread gracefully.
    """
    global _consumer_thread, _stop_consumer
    
    _stop_consumer.set()
    
    if _consumer_thread is not None:
        _consumer_thread.join(timeout=10)
        if _consumer_thread.is_alive():
            frappe.logger().warning("Consumer thread did not stop gracefully")
            kafka_logger.warning("Consumer thread did not stop gracefully") # [ADDED]
        else:
            frappe.logger().info("Consumer thread stopped")
            kafka_logger.info("Consumer thread stopped") # [ADDED]
        _consumer_thread = None
        
    close_consumer()


def get_consumer_status():
    """
    Returns the current status of the Kafka consumer.
    
    Returns:
        dict: Status information including running state and subscribed topics
    """
    global _consumer, _consumer_thread
    
    return {
        "kafka_available": KAFKA_AVAILABLE,
        "consumer_connected": _consumer is not None,
        "consumer_thread_running": _consumer_thread is not None and _consumer_thread.is_alive(),
        "subscribed_topics": CONSUME_TOPICS,
        "consumer_group_id": CONSUMER_GROUP_ID,
        "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS
    }


# ==========================================
# Frappe Commands / Hooks
# ==========================================

@frappe.whitelist()
def start_kafka_consumer():
    """
    Frappe whitelisted method to start the Kafka consumer.
    Can be called from the UI or via API.
    """
    try:
        success = start_consumer_thread()
        if success:
            return {"status": "success", "message": "Kafka consumer started"}
        else:
            return {"status": "warning", "message": "Consumer thread already running"}
    except Exception as e:
        error_logger.error(f"Start consumer failed: {str(e)}") # [ADDED]
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def stop_kafka_consumer():
    """
    Frappe whitelisted method to stop the Kafka consumer.
    """
    try:
        stop_consumer_thread()
        return {"status": "success", "message": "Kafka consumer stopped"}
    except Exception as e:
        error_logger.error(f"Stop consumer failed: {str(e)}") # [ADDED]
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_kafka_consumer_status():
    """
    Frappe whitelisted method to get consumer status.
    """
    return get_consumer_status()


@frappe.whitelist()
def consume_kafka_messages(max_messages=10):
    """
    Frappe whitelisted method to consume a specific number of messages.
    Useful for manual/batch processing.
    
    Args:
        max_messages: Maximum number of messages to consume
        
    Returns:
        dict: Result with number of messages processed
    """
    try:
        max_messages = int(max_messages)
        processed = consume_messages(max_messages=max_messages, timeout_ms=5000)
        return {
            "status": "success", 
            "messages_processed": processed
        }
    except Exception as e:
        error_logger.error(f"Consume messages failed: {str(e)}") # [ADDED]
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def reset_consumer_offset_to_beginning():
    """
    Frappe whitelisted method to reset consumer offset to beginning (offset 0).
    Useful for reprocessing all messages from the start.

    [UPDATED] Now resets offsets for ALL topics in CONSUME_TOPICS

    Returns:
        dict: Result with status
    """
    try:
        # Close global consumer if open to avoid conflicts
        close_consumer()

        from kafka import KafkaConsumer, TopicPartition

        # Create a fresh consumer WITHOUT subscribing (no topics in init)
        # Using the same GROUP ID to reset its offsets.
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=CONSUMER_GROUP_ID,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=False # We will commit manually
        )

        # =============================================================================
        # [UPDATED] Get partitions for ALL topics in CONSUME_TOPICS
        # =============================================================================
        all_tps = []
        topics_found = []

        for topic in CONSUME_TOPICS:
            partition_ids = consumer.partitions_for_topic(topic)
            if partition_ids:
                tps = [TopicPartition(topic, p) for p in partition_ids]
                all_tps.extend(tps)
                topics_found.append(topic)
                frappe.logger().info(f"Found {len(partition_ids)} partitions for topic {topic}")
                kafka_logger.info(f"Found {len(partition_ids)} partitions for topic {topic}") # [ADDED]
            else:
                frappe.logger().warning(f"No partitions found for topic {topic}")
                kafka_logger.warning(f"No partitions found for topic {topic}") # [ADDED]

        if not all_tps:
            consumer.close()
            error_logger.error(f"No partitions found for any topic in {CONSUME_TOPICS}") # [ADDED]
            return {"status": "error", "message": f"No partitions found for any topic in {CONSUME_TOPICS}"}

        # Assign all partitions
        consumer.assign(all_tps)
        frappe.logger().info(f"Assigned {len(all_tps)} partitions across {len(topics_found)} topics")
        kafka_logger.info(f"Assigned {len(all_tps)} partitions across {len(topics_found)} topics") # [ADDED]

        # Seek to beginning
        consumer.seek_to_beginning()

        # Verify position
        for tp in all_tps:
            pos = consumer.position(tp)
            frappe.logger().info(f"Topic {tp.topic} Partition {tp.partition} reset to offset {pos}")
            kafka_logger.info(f"Topic {tp.topic} Partition {tp.partition} reset to offset {pos}") # [ADDED]

        # Commit
        consumer.commit()
        frappe.logger().info("Offsets committed.")
        kafka_logger.info("Offsets committed.") # [ADDED]

        consumer.close()

        return {
            "status": "success",
            "message": f"Offsets reset to beginning for {len(all_tps)} partitions across {len(topics_found)} topics",
            "topics": topics_found,
            "total_partitions": len(all_tps)
        }
    except Exception as e:
        frappe.log_error(f"Error resetting consumer offset: {str(e)}", "Offset Reset Error")
        error_logger.error(f"Error resetting consumer offset: {str(e)}") # [ADDED]
        return {"status": "error", "message": str(e)}