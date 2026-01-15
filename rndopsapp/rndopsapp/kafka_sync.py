import frappe
import json
import time
from datetime import datetime, date
from frappe import _

try:
	from rndopsapp.rndopsapp.project_event_dto import ProjectEventDTO, ProjectDataDTO
except ImportError:
	# Fallback for standalone testing or different import context
	from project_event_dto import ProjectEventDTO, ProjectDataDTO

try:
	from kafka import KafkaProducer
	from kafka.admin import KafkaAdminClient, NewTopic
	from kafka.errors import TopicAlreadyExistsError
	KAFKA_AVAILABLE = True
except ImportError:
	KAFKA_AVAILABLE = False

# --- CONFIGURATION ---
# 3-Node Fault-Tolerant Cluster
KAFKA_BOOTSTRAP_SERVERS = [
	'172.16.135.118:9095',
	'172.16.135.118:9096'
]

# Topic Configuration
NUM_PARTITIONS = 2
REPLICATION_FACTOR = 2

# Topics
TOPIC_PROJECT = 'project-registration-events'
TOPIC_SANCTION = 'fund-sanction-events'
TOPIC_FUND_RECEIVED = 'fund-received-events'

# DLQ (Dead Letter Queue) Topics
TOPIC_PROJECT_DLQ = 'project-registration-events-dlq'
TOPIC_SANCTION_DLQ = 'fund-sanction-events-dlq'
TOPIC_FUND_RECEIVED_DLQ = 'fund-received-events-dlq'

# All Topics List
ALL_TOPICS = [
	TOPIC_PROJECT, TOPIC_PROJECT_DLQ,
	TOPIC_SANCTION, TOPIC_SANCTION_DLQ,
	TOPIC_FUND_RECEIVED, TOPIC_FUND_RECEIVED_DLQ
]

# Schema Versions
SCHEMA_VERSION_PROJECT = '1.0'
SCHEMA_VERSION_SANCTION = '1.0'
SCHEMA_VERSION_FUND_RECEIVED = '1.0'

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 1  # Exponential backoff base

# Singleton Producer Instance
_producer = None


def create_topics():
	"""
	Creates all required Kafka topics with proper replication factor.
	Safe to call multiple times - skips existing topics.
	"""
	if not KAFKA_AVAILABLE:
		print("kafka-python library not installed")
		return False

	try:
		admin_client = KafkaAdminClient(
			bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
			client_id='frappe-topic-creator'
		)

		# Get list of existing topics
		existing_topics = admin_client.list_topics()
		print(f"Existing topics: {existing_topics}")

		# Filter out topics that already exist
		topics_to_create = [topic for topic in ALL_TOPICS if topic not in existing_topics]

		if not topics_to_create:
			print("All topics already exist - skipping creation")
			admin_client.close()
			return True

		print(f"Creating missing topics: {topics_to_create}")

		# Create NewTopic objects for missing topics only
		new_topics = [
			NewTopic(
				name=topic,
				num_partitions=NUM_PARTITIONS,
				replication_factor=REPLICATION_FACTOR
			)
			for topic in topics_to_create
		]

		# Create topics
		result = admin_client.create_topics(new_topics=new_topics, validate_only=False)
		print(f"Topics created successfully: {topics_to_create}")
		admin_client.close()
		return True

	except Exception as e:
		print(f"Error creating topics: {e}")
		return False


def delete_topics():
	"""
	Deletes all Kafka topics. USE WITH CAUTION - this deletes all data!
	"""
	if not KAFKA_AVAILABLE:
		print("kafka-python library not installed")
		return False

	try:
		admin_client = KafkaAdminClient(
			bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
			client_id='frappe-topic-deleter'
		)

		admin_client.delete_topics(topics=ALL_TOPICS)
		print(f"Topics deleted: {ALL_TOPICS}")
		admin_client.close()
		return True

	except Exception as e:
		print(f"Error deleting topics: {e}")
		return False

def get_producer():
	"""
	Returns a singleton KafkaProducer instance.
	Reuses the same connection for all messages.
	"""
	global _producer
	
	if not KAFKA_AVAILABLE:
		frappe.log_error("kafka-python library not installed", "Kafka Sync Error")
		return None

	if _producer is not None:
		return _producer

	try:
		_producer = KafkaProducer(
			bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
			value_serializer=lambda v: json.dumps(v).encode('utf-8'),
			acks="all",       # Wait for leader acknowledgment (use 'all' for stricter durability)
			retries=3,    # Retry failed sends
			linger_ms=10  # Small batch window for better throughput
		)
		return _producer
	except Exception as e:
		frappe.log_error(f"Failed to connect to Kafka: {str(e)}", "Kafka Connection Error")
		return None

# def publish_message(topic, payload, doc_name, dlq_topic=None):
# 	"""
# 	Helper to publish a message to a Kafka topic with retry and DLQ support.
# 	Uses the singleton producer - does NOT close it after each message.
	
# 	Args:
# 		topic: Primary Kafka topic
# 		payload: Message payload (will be wrapped with metadata)
# 		doc_name: Document name for logging
# 		dlq_topic: Dead Letter Queue topic for failed messages
# 	"""
# 	producer = get_producer()
# 	if not producer:
# 		return False

# 	for attempt in range(MAX_RETRIES):
# 		try:
# 			future = producer.send(topic, payload)
# 			# Block for result to catch errors immediately
# 			record_metadata = future.get(timeout=10)
			
# 			frappe.logger().info(f"Kafka: Published {doc_name} to {topic} partition {record_metadata.partition} offset {record_metadata.offset}")
# 			return True
			
# 		except Exception as e:
# 			frappe.log_error(f"Attempt {attempt + 1}/{MAX_RETRIES} failed for {topic}: {str(e)}", "Kafka Publish Error")
			
# 			if attempt < MAX_RETRIES - 1:
# 				# Exponential backoff
# 				time.sleep(RETRY_DELAY_SECONDS * (2 ** attempt))
# 				# Reset producer on error so it reconnects
# 				global _producer
# 				_producer = None
# 				producer = get_producer()
# 				if not producer:
# 					break
	
# 	# All retries failed - send to DLQ
# 	if dlq_topic:
# 		try:
# 			producer = get_producer()
# 			if producer:
# 				# Add failure metadata to payload
# 				dlq_payload = {
# 					"originalTopic": topic,
# 					"failedAt": datetime.utcnow().isoformat(),
# 					"retryCount": MAX_RETRIES,
# 					"payload": payload
# 				}
# 				future = producer.send(dlq_topic, dlq_payload)
# 				future.get(timeout=10)
# 				frappe.logger().warning(f"Kafka: Sent {doc_name} to DLQ {dlq_topic}")
# 		except Exception as dlq_error:
# 			frappe.log_error(f"Failed to send to DLQ {dlq_topic}: {str(dlq_error)}", "Kafka DLQ Error")
	
# 	return False



def publish_message(topic, payload, doc_name, dlq_topic=None, key=None):
    """
    Helper to publish a message to a Kafka topic with key-based partitioning, 
    retry logic, and DLQ support.
    
    Args:
        topic: Primary Kafka topic (e.g., 'fund-received-events')
        payload: The dictionary data (will be JSON serialized by producer)
        doc_name: Frappe document name for logging (e.g., FR-2026-0001)
        dlq_topic: Topic to send to if all retries fail
        key: The partitioning key (use Project Number) to ensure message ordering
    """
    global _producer
    producer = get_producer()
    if not producer:
        frappe.log_error(f"Kafka Producer not available for {doc_name}", "Kafka Error")
        return False

    # 1. Prepare the Key
    # All messages with the same key go to the same partition to maintain order
    kafka_key = str(key).encode('utf-8') if key else None

    # 2. Attempt Publication with Retries
    for attempt in range(MAX_RETRIES):
        try:
            # send() is asynchronous; it returns a future
            future = producer.send(topic, key=kafka_key, value=payload)
            
            # .get() makes it synchronous, waiting up to 10s for the broker to acknowledge
            record_metadata = future.get(timeout=10)
            
            frappe.logger().info(
                f"Kafka Success: {doc_name} -> {topic} | "
                f"Partition: {record_metadata.partition} | "
                f"Offset: {record_metadata.offset}"
            )
            return True
            
        except Exception as e:
            error_details = f"Attempt {attempt + 1}/{MAX_RETRIES} failed for {topic}: {str(e)}"
            frappe.log_error(error_details, "Kafka Publish Error")
            
            if attempt < MAX_RETRIES - 1:
                # Exponential backoff: 1s, 2s, 4s...
                time.sleep(RETRY_DELAY_SECONDS * (2 ** attempt))
                
                # Reset producer on network/connection errors to force a fresh connection
                _producer = None
                producer = get_producer()
                if not producer:
                    break
    
    # 3. Handle Failure: Send to Dead Letter Queue (DLQ)
    if dlq_topic:
        try:
            producer = get_producer() # Attempt one last grab of the producer
            if producer:
                dlq_payload = {
                    "originalTopic": topic,
                    "failedAt": datetime.utcnow().isoformat(),
                    "retryCount": MAX_RETRIES,
                    "error": str(e) if 'e' in locals() else "Unknown Error",
                    "payload": payload
                }
                # Send to DLQ using the same key to keep it associated with the project
                future = producer.send(dlq_topic, key=kafka_key, value=dlq_payload)
                future.get(timeout=10)
                frappe.logger().warning(f"Kafka: Sent {doc_name} to DLQ {dlq_topic} after {MAX_RETRIES} attempts")
        except Exception as dlq_error:
            frappe.log_error(f"CRITICAL: Failed to send to DLQ {dlq_topic}: {str(dlq_error)}", "Kafka DLQ Error")
    
    return False


def validate_required_fields(data, required_fields, doc_name):
	"""
	Validates that required fields are present and not empty.
	Returns (is_valid, error_message)
	"""
	missing_fields = []
	for field in required_fields:
		value = data.get(field) if isinstance(data, dict) else getattr(data, field, None)
		if value is None or value == "":
			missing_fields.append(field)
	
	if missing_fields:
		error_msg = f"Missing required fields for {doc_name}: {', '.join(missing_fields)}"
		frappe.log_error(error_msg, "Kafka Validation Error")
		return False, error_msg
	
	return True, None

# ==========================================
# 1. Projects
# ==========================================

def publish_project(doc, method=None):
	"""
	Feeds from: Project Registration
	Topic: project-registration-events
	Uses ProjectEventDTO for structured validation and serialization.
	"""
	if not KAFKA_AVAILABLE: return

	try:
		# Validate required fields
		required_fields = ['name', 'pi_employee_id', 'project_type']
		is_valid, error = validate_required_fields(doc, required_fields, doc.name)
		if not is_valid:
			return False

		# Map Child Table: Implemented Dept Centres (if exists)
		dept_centres = []
		# Adjust field name based on actual doctype definition if needed
		# if hasattr(doc, 'department_centres'): ...
		
		# Fetch actual dept_id from Department_prornd
		department_id = doc.applicant_department
		try:
			if doc.applicant_department:
				department_id = frappe.db.get_value("Department_prornd", doc.applicant_department, "dept_id") or doc.applicant_department
		except Exception:
			pass

		# Parse dates safely
		start_date = None
		completion_date = None
		apply_date = doc.creation if doc.creation else datetime.utcnow()

		# Build ProjectDataDTO
		project_data = ProjectDataDTO(
			projectNumber=doc.name,
			empId=doc.pi_employee_id or "",
			departmentId=department_id or "",
			projectType=doc.project_type or "",
			projectCategory=doc.consultancy_category,
			fundingAgencyType=doc.funding_agency_type or "",
			fundingAgencyId=doc.funding_agen or "",
			projectScheme=doc.funding_agency_schemes or "",
			totalBudgetAmount=float(doc.total_budget_amount or 0),
			overHeadAmountPercentage=float(doc.overhead_percentage_research or doc.overhead_percentage_consultancy or 0),
			overHeadAmount=float(doc.overhead_research or doc.overhead_consultancy or 0),
			budgetWithOverHeadAmount=float(doc.budget_including_overhead_research or doc.budget_including_overhead_consultancy or 0),
			gst=float(doc.service_tax_research or doc.service_tax_consultancy or 0),
			grandTotal=float(doc.grand_total_research or doc.grand_total_consultancy or 0),
			startDate=start_date,
			completionDate=completion_date,
			durationMonths=doc.project_duration_months,
			status=doc.workflow_state or "",
			applyDate=apply_date,
			implementedDeptCentres=dept_centres
		)

		# Build ProjectEventDTO
		event = ProjectEventDTO(
			schemaVersion=SCHEMA_VERSION_PROJECT,
			eventType="PROJECT_REGISTRATION",
			timestamp=datetime.utcnow(),
			data=project_data
		)

		# Convert to dict for Kafka serialization (using model_dump for Pydantic v2)
		wrapped_payload = event.model_dump(mode="json")

		return publish_message(TOPIC_PROJECT, wrapped_payload, doc.name, TOPIC_PROJECT_DLQ)

	except Exception as e:
		frappe.log_error(f"Error preparing project payload: {str(e)}", "Kafka Sync Error")
		return False

# ==========================================
# 2. Sanction Details
# ==========================================

def publish_sanction(doc, method=None):
	"""
	Feeds from: Fund Sanction
	Topic: fund-sanction-events
	"""
	print(f"\n🚀 [KAFKA] publish_sanction called for doc: {doc.name}")
	
	if not KAFKA_AVAILABLE:
		print("❌ [KAFKA] kafka-python library not available")
		return False

	try:
		# Get project number - use refnum_prj_num or fallback to project_proposal
		project_number = doc.refnum_prj_num or doc.project_proposal
		sanction_letter_no = doc.sanctioned_letter_no
		
		print(f"📋 [KAFKA] project_number: {project_number}")
		print(f"📋 [KAFKA] sanction_letter_no: {sanction_letter_no}")
		print(f"📋 [KAFKA] total_sanctioned_amount: {doc.total_sanctioned_amount}")
		print(f"📋 [KAFKA] sanctioned_letter_date: {doc.sanctioned_letter_date}")
		
		# Validate required fields - only name is strictly required
		if not doc.name:
			print("❌ [KAFKA] Validation failed: missing doc name")
			return False
		
		if not project_number:
			print("⚠️ [KAFKA] Warning: no project number available (refnum_prj_num and project_proposal both empty)")

		# Map Child Table: Budget Breakups
		budget_breakups = []
		if hasattr(doc, 'sanctioned_budget_breakup'):
			print(f"📋 [KAFKA] Processing {len(doc.sanctioned_budget_breakup)} budget breakup rows")
			for row in doc.sanctioned_budget_breakup:
				# Safely get b_id. DO NOT use row.id as that is the row's unique name/timestamp.
				account_head_id = getattr(row, 'b_id', None)
				
				# If b_id is missing, fetch the 'id' from the linked Budget Head document
				if account_head_id is None and row.account_head:
					try:
						# Fetch 'id' from Budget Head using the link field 'account_head'
						account_head_id = frappe.db.get_value("Budget Head", row.account_head, "id")
						
						# Fallback: try filtering by 'budget_head' field if name lookup fails
						if not account_head_id:
							account_head_id = frappe.db.get_value("Budget Head", {"budget_head": row.account_head}, "id")
						
						# Fallback 2: Try plural/singular variations (e.g. Equipment vs Equipments)
						if not account_head_id:
							val = row.account_head
							if val.endswith("s"):
								# Try removing 's'
								account_head_id = frappe.db.get_value("Budget Head", {"budget_head": val[:-1]}, "id")
							else:
								# Try adding 's'
								account_head_id = frappe.db.get_value("Budget Head", {"budget_head": val + "s"}, "id")
							
						if account_head_id is None:
							frappe.logger().warning(f"⚠️ Could not find Budget Head ID for '{row.account_head}'")
							print(f"⚠️ Could not find Budget Head ID for '{row.account_head}'")
						else:
							print(f"✅ Found Budget Head ID {account_head_id} for '{row.account_head}'")
							
					except Exception as e:
						frappe.logger().warning(f"Failed to fetch Budget Head ID for {row.account_head}: {e}")

				budget_breakups.append({
					"accountHeadId": account_head_id,
					"accountHeadAmount": float(row.total_proposal_of_heads or 0),
					"firstYearBudget": float(row.first_year_budget or 0),
					"secondYearBudget": float(row.second_year_budget or 0),
					"thirdYearBudget": float(row.third_year_budget or 0),
					"fourthYearBudget": float(row.fourth_year_budget or 0),
					"fifthYearBudget": float(row.fifth_year_budget or 0)
				})
		else:
			print("📋 [KAFKA] No sanctioned_budget_breakup found on doc")

		payload = {
			"projectNumber": project_number,
			"sanctionLetterNo": sanction_letter_no,
			"sanctionLetterDate": str(doc.sanctioned_letter_date) if doc.sanctioned_letter_date else None,
			"totalSanctionAmount": float(doc.total_sanctioned_amount or 0),
			"budgetBreakups": budget_breakups
		}
		
		print(f"📦 [KAFKA] Payload prepared: {payload}")
		
		# Wrap payload with schema metadata
		wrapped_payload = {
			"schemaVersion": SCHEMA_VERSION_SANCTION,
			"eventType": "FUND_SANCTION",
			"timestamp": datetime.utcnow().isoformat(),
			"data": payload
		}

		print(f"📤 [KAFKA] Sending to topic: {TOPIC_SANCTION}")
		result = publish_message(TOPIC_SANCTION, wrapped_payload, doc.name, TOPIC_SANCTION_DLQ)
		print(f"{'✅' if result else '❌'} [KAFKA] publish_message returned: {result}")
		return result

	except Exception as e:
		error_msg = f"Error preparing sanction payload: {str(e)}"
		print(f"❌ [KAFKA] {error_msg}")
		frappe.log_error(error_msg, "Kafka Sync Error")
		return False

# ==========================================
# 3. Fund Received
# ==========================================

def publish_fund_received(doc, method=None):
	"""
	Feeds from: Fund Received
	Topic: fund-received-events
	
	Correct Structure for fund received:
	{
		"sanctionLetterNo": "SAN-2026-001",
		"projectNumber": "TEST-PRJ-1110",
		"amountReceived": 50000.00,
		"iitgAccountNumber": "IITG-ACC-001",
		"depositSlipStatus": false,
		"fundReceivedStatus": "PENDING_APPROVAL",
		"depositeStatusUpdateTime": "2026-01-08T10:15:30.123456",
		"fundReceivedStatusUpdateTime": "2026-01-08T10:15:30.123456",
		"fundBudgetBreakupList": [...],
		"transactionDetailsList": [...]
	}
	"""
	print(f"\n🚀 [KAFKA] publish_fund_received called for doc: {doc.name}")
	
	if not KAFKA_AVAILABLE:
		print("❌ [KAFKA] kafka-python library not available")
		return False

	try:
		# Debug: Print document fields
		print(f"📋 [KAFKA] prjreg_title: {getattr(doc, 'prjreg_title', None)}")
		print(f"📋 [KAFKA] sanction_ref_no: {getattr(doc, 'sanction_ref_no', None)}")
		print(f"📋 [KAFKA] fund_received_amt: {getattr(doc, 'fund_received_amt', None)}")
		
		# Validate required fields - only name and prjreg_title are strictly required
		if not doc.name:
			print("❌ [KAFKA] Validation failed: missing doc name")
			return False
			
		if not getattr(doc, 'prjreg_title', None):
			print("⚠️ [KAFKA] Warning: prjreg_title is empty")

		# Get sanction letter details - first check if Fund Received has its own fields
		sanction_letter_no = getattr(doc, 'sanctioned_letter_no', None)
		
		# If not available, fetch from linked Fund Sanction document
		sanction_ref = getattr(doc, 'sanction_ref_no', None)
		if sanction_ref and not sanction_letter_no:
			print(f"📋 [KAFKA] Fetching sanction details for: {sanction_ref}")
			try:
				sanction_doc = frappe.db.get_value(
					"Fund Sanction", 
					sanction_ref, 
					["sanctioned_letter_no"], 
					as_dict=True
				)
				if sanction_doc:
					sanction_letter_no = sanction_doc.get("sanctioned_letter_no")
					print(f"✅ [KAFKA] Got sanction letter_no: {sanction_letter_no}")
				else:
					print(f"⚠️ [KAFKA] No Fund Sanction found for: {sanction_ref}")
			except Exception as e:
				print(f"⚠️ [KAFKA] Failed to fetch sanction details for {sanction_ref}: {e}")
				frappe.logger().warning(f"Failed to fetch sanction details for {sanction_ref}: {e}")

		# Build fundBudgetBreakupList
		fund_budget_breakup_list = []
		if hasattr(doc, 'received_amt_breakup') and doc.received_amt_breakup:
			print(f"📋 [KAFKA] Processing {len(doc.received_amt_breakup)} budget breakup rows")
			for row in doc.received_amt_breakup:
				# Safely get b_id
				account_head_id = getattr(row, 'b_id', None)
				
				# If b_id is missing, fetch the 'id' from the linked Budget Head document
				if account_head_id is None and row.account_head:
					try:
						# Fetch 'id' from Budget Head using the link field 'account_head'
						account_head_id = frappe.db.get_value("Budget Head", row.account_head, "id")
						
						# Fallback: try filtering by 'budget_head' field if name lookup fails
						if not account_head_id:
							account_head_id = frappe.db.get_value("Budget Head", {"budget_head": row.account_head}, "id")
						
						# Fallback 2: Try plural/singular variations (e.g. Equipment vs Equipments)
						if not account_head_id:
							val = row.account_head
							if val.endswith("s"):
								account_head_id = frappe.db.get_value("Budget Head", {"budget_head": val[:-1]}, "id")
							else:
								account_head_id = frappe.db.get_value("Budget Head", {"budget_head": val + "s"}, "id")
							
						if account_head_id is None:
							frappe.logger().warning(f"⚠️ Could not find Budget Head ID for '{row.account_head}'")
							print(f"⚠️ Could not find Budget Head ID for '{row.account_head}'")
						else:
							print(f"✅ Found Budget Head ID {account_head_id} for '{row.account_head}'")
							
					except Exception as e:
						frappe.logger().warning(f"Failed to fetch Budget Head ID for {row.account_head}: {e}")

				# Get the amount from Fund Received child table
				amount = float(getattr(row, 'amount_received', 0) or 0)
				remarks = getattr(row, 'remarks', None) or getattr(row, 'description', None) or ""
				
				print(f"📋 [KAFKA] Row: account_head={row.account_head}, amount={amount}")
				
				fund_budget_breakup_list.append({
					"accountHeadId": str(account_head_id) if account_head_id else None,
					"amount": amount,
					"remarks": remarks
				})
		else:
			print("📋 [KAFKA] No received_amt_breakup found on doc")

		# Build transactionDetailsList from 'fund_transactions' child table (Project Fund Transaction)
		# Fields: transaction_number, transaction_date, amount
		transaction_details_list = []
		if hasattr(doc, 'fund_transactions') and doc.fund_transactions:
			print(f"📋 [KAFKA] Processing {len(doc.fund_transactions)} transaction detail rows")
			for row in doc.fund_transactions:
				# Using correct field names from Project Fund Transaction doctype
				unique_txn_number = getattr(row, 'transaction_number', "") or ""
				txn_date = getattr(row, 'transaction_date', None)
				txn_amount = float(getattr(row, 'amount', 0) or 0)
				
				transaction_details_list.append({
					"uniqueTransactionNumber": unique_txn_number,
					"transactionReceivedDate": str(txn_date) if txn_date else None,
					"transactionAmount": txn_amount
				})
		else:
			# If no child table, create single transaction from main fields
			print("📋 [KAFKA] No fund_transactions child table found")

		# Get current timestamp for status update times
		current_timestamp = datetime.utcnow().isoformat()
		
		# Build the payload with the correct structure
		# Using correct field names from Fund Received doctype:
		# - bank_account: Bank Account Number (maps to iitgAccountNumber)
		# - workflow_state: Status (maps to fundReceivedStatus)
		payload = {
			# "fundReceivedRefNumber": doc.name,  # Mapped from autoname
			"sanctionLetterNo": sanction_letter_no,
			"projectNumber": doc.prjreg_title,  # Link field stores project name
			"amountReceived": float(getattr(doc, 'fund_received_amt', 0) or 0),
			"iitgAccountNumber": getattr(doc, 'bank_account', None) or "",
			"depositSlipStatus": False,  # No deposit_slip_status field in Fund Received doctype
			"fundReceivedStatus": getattr(doc, 'workflow_state', None) or "PENDING_APPROVAL",
			"depositeStatusUpdateTime": current_timestamp,
			"fundReceivedStatusUpdateTime": current_timestamp,
			"fundBudgetBreakupList": fund_budget_breakup_list,
			"transactionDetailsList": transaction_details_list
		}
		
		print(f"📦 [KAFKA] Payload prepared: {payload}")
		
		# Wrap payload with schema metadata
		wrapped_payload = {
			"schemaVersion": SCHEMA_VERSION_FUND_RECEIVED,
			"eventType": "FUND_RECEIVED",
			"timestamp": datetime.utcnow().isoformat(),
			"data": payload
		}

		print(f"📤 [KAFKA] Sending to topic: {TOPIC_FUND_RECEIVED}")
		result = publish_message(TOPIC_FUND_RECEIVED, wrapped_payload, doc.name, TOPIC_FUND_RECEIVED_DLQ)
		print(f"{'✅' if result else '❌'} [KAFKA] publish_message returned: {result}")
		return result

	except Exception as e:
		error_msg = f"Error preparing fund received payload: {str(e)}"
		print(f"❌ [KAFKA] {error_msg}")
		frappe.log_error(error_msg, "Kafka Sync Error")
		return False

