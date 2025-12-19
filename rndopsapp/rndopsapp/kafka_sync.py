import frappe
import json
import time
from datetime import datetime
from frappe import _

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
	'172.16.135.118:9096',
	'172.16.135.118:9097'
]

# Topic Configuration
NUM_PARTITIONS = 3
REPLICATION_FACTOR = 3

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

		# Create NewTopic objects
		new_topics = [
			NewTopic(
				name=topic,
				num_partitions=NUM_PARTITIONS,
				replication_factor=REPLICATION_FACTOR
			)
			for topic in ALL_TOPICS
		]

		# Create topics
		result = admin_client.create_topics(new_topics=new_topics, validate_only=False)
		print(f"Topics created successfully: {ALL_TOPICS}")
		admin_client.close()
		return True

	except TopicAlreadyExistsError:
		print("Some topics already exist - skipping")
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

def publish_message(topic, payload, doc_name, dlq_topic=None):
	"""
	Helper to publish a message to a Kafka topic with retry and DLQ support.
	Uses the singleton producer - does NOT close it after each message.
	
	Args:
		topic: Primary Kafka topic
		payload: Message payload (will be wrapped with metadata)
		doc_name: Document name for logging
		dlq_topic: Dead Letter Queue topic for failed messages
	"""
	producer = get_producer()
	if not producer:
		return False

	for attempt in range(MAX_RETRIES):
		try:
			future = producer.send(topic, payload)
			# Block for result to catch errors immediately
			record_metadata = future.get(timeout=10)
			
			frappe.logger().info(f"Kafka: Published {doc_name} to {topic} partition {record_metadata.partition} offset {record_metadata.offset}")
			return True
			
		except Exception as e:
			frappe.log_error(f"Attempt {attempt + 1}/{MAX_RETRIES} failed for {topic}: {str(e)}", "Kafka Publish Error")
			
			if attempt < MAX_RETRIES - 1:
				# Exponential backoff
				time.sleep(RETRY_DELAY_SECONDS * (2 ** attempt))
				# Reset producer on error so it reconnects
				global _producer
				_producer = None
				producer = get_producer()
				if not producer:
					break
	
	# All retries failed - send to DLQ
	if dlq_topic:
		try:
			producer = get_producer()
			if producer:
				# Add failure metadata to payload
				dlq_payload = {
					"originalTopic": topic,
					"failedAt": datetime.utcnow().isoformat(),
					"retryCount": MAX_RETRIES,
					"payload": payload
				}
				future = producer.send(dlq_topic, dlq_payload)
				future.get(timeout=10)
				frappe.logger().warning(f"Kafka: Sent {doc_name} to DLQ {dlq_topic}")
		except Exception as dlq_error:
			frappe.log_error(f"Failed to send to DLQ {dlq_topic}: {str(dlq_error)}", "Kafka DLQ Error")
	
	return False

# ==========================================
# 1. Projects
# ==========================================

def publish_project(doc, method=None):
	"""
	Feeds from: Project Registration
	Topic: project-registration-events
	"""
	if not KAFKA_AVAILABLE: return

	try:
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

		# Map payload
		payload = {
			"projectNumber": doc.name,
			"empId": doc.pi_employee_id,
			"departmentId": department_id,
			"projectType": doc.project_type,
			"projectCategory": doc.consultancy_category,
			"fundingAgencyType": doc.funding_agency_type,
			"fundingAgencyId": doc.funding_agen,
			"projectScheme": doc.funding_agency_schemes,
			"totalBudgetAmount": float(doc.total_budget_amount or 0),
			
			# Handle research vs consultancy overhead fields
			"overHeadAmountPercentage": float(doc.overhead_percentage_research or doc.overhead_percentage_consultancy or 0),
			"overHeadAmount": float(doc.overhead_research or doc.overhead_consultancy or 0),
			"budgetWithOverHeadAmount": float(doc.budget_including_overhead_research or doc.budget_including_overhead_consultancy or 0),
			"gst": float(doc.service_tax_research or doc.service_tax_consultancy or 0),
			"grandTotal": float(doc.grand_total_research or doc.grand_total_consultancy or 0),
			
			"startDate": None, # Not directly in doc, maybe calculate?
			"completionDate": None,
			"durationMonths": doc.project_duration_months,
			
			"status": doc.workflow_state,
			"applyDate": str(doc.creation),
			"implementedDeptCentres": dept_centres
		}
		# Wrap payload with schema metadata
		wrapped_payload = {
			"schemaVersion": SCHEMA_VERSION_PROJECT,
			"eventType": "PROJECT_REGISTRATION",
			"timestamp": datetime.utcnow().isoformat(),
			"data": payload
		}

		publish_message(TOPIC_PROJECT, wrapped_payload, doc.name, TOPIC_PROJECT_DLQ)

	except Exception as e:
		frappe.log_error(f"Error preparing project payload: {str(e)}", "Kafka Sync Error")

# ==========================================
# 2. Sanction Details
# ==========================================

def publish_sanction(doc, method=None):
	"""
	Feeds from: Fund Sanction
	Topic: fund-sanction-events
	"""
	if not KAFKA_AVAILABLE: return

	try:
		# Map Child Table: Budget Breakups
		budget_breakups = []
		if hasattr(doc, 'sanctioned_budget_breakup'):
			for row in doc.sanctioned_budget_breakup:
				budget_breakups.append({
					"accountHeadId": row.account_head,
					"accountHeadAmount": float(row.total_proposal_of_heads or 0),
					"firstYearBudget": float(row.first_year_budget or 0),
					"secondYearBudget": float(row.second_year_budget or 0),
					"thirdYearBudget": float(row.third_year_budget or 0),
					"fourthYearBudget": float(row.fourth_year_budget or 0),
					"fifthYearBudget": float(row.fifth_year_budget or 0)
				})

		payload = {
			"projectNumber": doc.refnum_prj_num,
			"sanctionLetterNo": doc.sanctioned_letter_no,
			"sanctionLetterDate": str(doc.sanctioned_letter_date),
			"totalSanctionAmount": float(doc.total_sanctioned_amount or 0),
			"budgetBreakups": budget_breakups
		}
		# Wrap payload with schema metadata
		wrapped_payload = {
			"schemaVersion": SCHEMA_VERSION_SANCTION,
			"eventType": "FUND_SANCTION",
			"timestamp": datetime.utcnow().isoformat(),
			"data": payload
		}

		publish_message(TOPIC_SANCTION, wrapped_payload, doc.name, TOPIC_SANCTION_DLQ)

	except Exception as e:
		frappe.log_error(f"Error preparing sanction payload: {str(e)}", "Kafka Sync Error")

# ==========================================
# 3. Fund Received
# ==========================================

def publish_fund_received(doc, method=None):
	"""
	Feeds from: Fund Received
	Topic: fund-received-events
	"""
	if not KAFKA_AVAILABLE: return

	try:
		# Child Table: Fund Budget Breakup
		fund_breakups = []
		if hasattr(doc, 'received_amt_breakup'):
			for row in doc.received_amt_breakup:
				fund_breakups.append({
					"accountHeadId": row.account_head,
					"amount": float(row.amount_received or 0),
					"remarks": row.remarks
				})

		# Child Table: Transaction Details
		txn_details = []
		if hasattr(doc, 'fund_transactions'):
			for row in doc.fund_transactions:
				txn_details.append({
					"uniqueTransactionNumber": row.transaction_number,
					"transactionReceivedDate": str(row.transaction_date),
					"transactionAmount": float(row.amount or 0)
				})

		payload = {
			"sanctionNumber": doc.sanction_ref_no,
			"projectNumber": doc.prjreg_title, # Link field stores name
			"amountReceived": float(doc.fund_received_amt or 0),
			"iitgAccountNumber": doc.bank_account,
			"fundBudgetBreakupList": fund_breakups,
			"transactionDetailsList": txn_details
		}
		# Wrap payload with schema metadata
		wrapped_payload = {
			"schemaVersion": SCHEMA_VERSION_FUND_RECEIVED,
			"eventType": "FUND_RECEIVED",
			"timestamp": datetime.utcnow().isoformat(),
			"data": payload
		}

		publish_message(TOPIC_FUND_RECEIVED, wrapped_payload, doc.name, TOPIC_FUND_RECEIVED_DLQ)

	except Exception as e:
		frappe.log_error(f"Error preparing fund received payload: {str(e)}", "Kafka Sync Error")
