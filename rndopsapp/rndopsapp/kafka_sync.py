import frappe
import json
import time
from datetime import datetime, date
from frappe import _
from rndopsapp.config import KAFKA_BOOTSTRAP_SERVERS

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
# Kafka Bootstrap Servers (imported from centralized config)

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
	TOPIC_FUND_RECEIVED, TOPIC_FUND_RECEIVED_DLQ,
	'deposit-slip-events', 'deposit-slip-events-dlq'
]

# Schema Versions
SCHEMA_VERSION_PROJECT = '1.0'
SCHEMA_VERSION_SANCTION = '1.0'
SCHEMA_VERSION_FUND_RECEIVED = '1.0'

# Retry Configuration
# NOTE: KafkaProducer already has internal retries=3 at the protocol level.
# Application-level retries cause duplicate messages when broker ack times out
# but message was already written. Set to 1 (no retry) to prevent duplicates.
MAX_RETRIES = 1
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
		imp_dept = getattr(doc, "implementation_department", None)

		# Helper to resolve dept_id
		def get_dept_id(dept_link):
			if not dept_link: return None
			# Attempt to get numeric ID
			val = frappe.db.get_value("Department_prornd", dept_link, "dept_id")
			return val

		# Check if it's a list (Child Table)
		if isinstance(imp_dept, list):
			for row in imp_dept:
				# Child table field is usually 'department'
				d_link = getattr(row, "department", None)
				d_id = get_dept_id(d_link)
				if d_id:
					dept_centres.append(str(d_id))  # Simple string ID format
		# Check if it's a single link
		elif isinstance(imp_dept, str) and imp_dept:
			d_id = get_dept_id(imp_dept)
			if d_id:
				dept_centres.append(str(d_id))  # Simple string ID format

		# Extract the primary department_id from the first department in the list
		department_id = None
		if dept_centres:
			department_id = dept_centres[0]  # First ID from the list

		# Helper to resolve funding_agency_id from linked fundingagency_ doctype
		def get_funding_agency_id(funding_agen_link):
			if not funding_agen_link:
				return None
			# Fetch funding_agency_id from the linked fundingagency_ document
			return frappe.db.get_value("fundingagency_", funding_agen_link, "funding_agency_id")

		# Get funding_agency_id - first try from doc, then fetch from linked doctype
		funding_agency_id = getattr(doc, "funding_agency_id", None)
		if not funding_agency_id:
			funding_agen_link = getattr(doc, "funding_agen", None)
			if funding_agen_link:
				funding_agency_id = get_funding_agency_id(funding_agen_link)
				if funding_agency_id:
					print(f"✅ Fetched funding_agency_id: {funding_agency_id} from fundingagency_: {funding_agen_link}")
				else:
					print(f"⚠️ Could not find funding_agency_id for fundingagency_: {funding_agen_link}")

		# Parse dates safely
		start_date = doc.prj_start_date or doc.start_date
		completion_date = doc.prj_end_date or doc.completion_date
		
		# Apply/Verdict Dates
		apply_date = doc.creation if doc.creation else datetime.utcnow()
		verdict_date = doc.verdict_date if hasattr(doc, 'verdict_date') else None
		if not verdict_date and doc.workflow_state == "Approved":
			verdict_date = datetime.now().date()

		# Determine project type and category for conditional field mapping
		is_consultancy = doc.project_type == "Consultancy"
		consultancy_category = getattr(doc, 'consultancy_category', '')
		is_category_d = is_consultancy and 'Category D' in consultancy_category
		is_category_ef = is_consultancy and ('Category E' in consultancy_category or 'Category F' in consultancy_category)

		# Map GSTIN based on project type
		gstin_number = doc.consultancy_gstin if is_consultancy and doc.consultancy_gstin else getattr(doc, 'gstin_number', '')

		# Helper function to calculate budget amounts
		def calculate_budget_amounts(total_budget_amount, overhead_amount, gst_amount):
			"""
			Calculate totalBudgetAmount and overHeadAmountPercentage.
			
			Args:
				total_budget_amount: The original total budget amount from doc.total_budget_amount
				overhead_amount: The overhead amount for the budget head
				gst_amount: The GST amount for the budget head
			
			Returns:
				tuple: (calculated_total_budget_amount, overhead_percentage)
				- calculated_total_budget_amount = total_budget_amount - (overhead_amount + gst_amount)
				- overhead_percentage = (overhead_amount / total_budget_amount) * 100 (if total_budget_amount > 0)
			"""
			# Calculate total budget amount excluding overhead and GST
			calculated_total = total_budget_amount - (overhead_amount + gst_amount)
			
			# Calculate overhead percentage relative to total budget amount
			if total_budget_amount > 0:
				overhead_pct = (overhead_amount / total_budget_amount) * 100
			else:
				overhead_pct = 0.0
			
			return calculated_total, overhead_pct

		# Get the base total budget amount from doc
		base_total_budget = float(doc.total_budget_amount or 0)

		# Map financial fields based on category
		if is_category_d:
			# Category D: Technology Transfer / Research Based
			overhead_amount = float(getattr(doc, 'cat_d_total_overhead', 0) or 0)
			gst_amount = float(getattr(doc, 'cat_d_gst_amt', 0) or 0)
			grand_total = float(getattr(doc, 'cat_d_grand_total_calc', 0) or 0)
			budget_with_overhead = float(getattr(doc, 'cat_d_project_cost_excl_gst', 0) or 0)
			# Calculate total budget and overhead percentage
			calculated_total_budget, overhead_percentage = calculate_budget_amounts(base_total_budget, overhead_amount, gst_amount)
		elif is_category_ef:
			# Category E/F: Non-routine / Testing
			overhead_amount = 0.0
			gst_amount = float(getattr(doc, 'cat_ef_gst', 0) or 0)
			grand_total = float(getattr(doc, 'cat_ef_grand_total', 0) or 0)
			budget_with_overhead = float(getattr(doc, 'cat_ef_total_amount', 0) or 0)
			# Calculate total budget and overhead percentage (overhead is 0 for E/F)
			calculated_total_budget, overhead_percentage = calculate_budget_amounts(base_total_budget, overhead_amount, gst_amount)
		else:
			# Research projects or other consultancy categories
			# First try document-level fields
			overhead_amount = float(doc.overhead_research or doc.overhead_consultancy or 0)
			gst_amount = float(doc.service_tax_research or doc.service_tax_consultancy or 0)
			
			# If document-level fields are 0, extract from proposed_budget_breakup child table
			if overhead_amount == 0 or gst_amount == 0:
				budget_breakup = getattr(doc, 'proposed_budget_breakup', []) or []
				for row in budget_breakup:
					account_head = getattr(row, 'account_head', '').strip().lower()
					row_amount = float(getattr(row, 'total_proposal_of_heads', 0) or 0)
					
					if overhead_amount == 0 and account_head == 'overhead':
						overhead_amount = row_amount
						print(f"📋 [KAFKA] Extracted overhead from budget breakup: {overhead_amount}")
					elif gst_amount == 0 and account_head == 'gst':
						gst_amount = row_amount
						print(f"📋 [KAFKA] Extracted GST from budget breakup: {gst_amount}")
			
			grand_total = float(doc.total_budget_amount or doc.grand_total_consultancy or 0)
			budget_with_overhead = float(doc.budget_including_overhead_research or doc.budget_including_overhead_consultancy or 0)
			
			# If budget_with_overhead is 0, calculate as: sum of all budget heads - GST
			if budget_with_overhead == 0:
				budget_with_overhead = base_total_budget - gst_amount
				print(f"📋 [KAFKA] Calculated budgetWithOverHeadAmount: {budget_with_overhead} (total: {base_total_budget} - GST: {gst_amount})")
			
			# Calculate total budget and overhead percentage
			calculated_total_budget, overhead_percentage = calculate_budget_amounts(base_total_budget, overhead_amount, gst_amount)

		# Build ProjectDataDTO
		project_data = ProjectDataDTO(
			projectNumber=doc.name,
			empId=doc.pi_employee_id or "",
			departmentId=department_id or "",
			projectType=doc.project_type or "",
			projectCategory=doc.consultancy_category or doc.project_type or "",
			fundingAgencyType=doc.funding_agency_type or "",
			#fundingAgencyId=doc.funding_agen or "",
			fundingAgencyId=funding_agency_id or "",
			projectScheme=doc.funding_agency_schemes or "",
			totalBudgetAmount=calculated_total_budget,
			overHeadAmountPercentage=overhead_percentage,
			overHeadAmount=overhead_amount,
			budgetWithOverHeadAmount=budget_with_overhead,
			gst=gst_amount,
			grandTotal=grand_total,
			startDate=start_date,
			completionDate=completion_date,
			durationMonths=str(doc.project_duration_months) if doc.project_duration_months else "0",
			durationInDays=str(doc.project_duration_days) if doc.project_duration_days else "0",
			# gstinNumber=gstin_number,  # Not needed in Kafka
			# projectImplementationLocation=getattr(doc, 'project_implementation_location', 'Guwahati,Assam'),  //MKY 27-01-2026
			# verdictDate=verdict_date, //MKY 27-01-2026
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

				# Get year budgets
				first_year = float(row.first_year_budget or 0)
				second_year = float(row.second_year_budget or 0)
				third_year = float(row.third_year_budget or 0)
				fourth_year = float(row.fourth_year_budget or 0)
				fifth_year = float(row.fifth_year_budget or 0)
				
				# Calculate accountHeadAmount: use total_proposal_of_heads if available, else sum of year budgets
				account_head_amount = float(row.total_proposal_of_heads or 0)
				if account_head_amount == 0:
					account_head_amount = first_year + second_year + third_year + fourth_year + fifth_year
					print(f"📋 [KAFKA] Calculated accountHeadAmount for {row.account_head}: {account_head_amount}")

				budget_breakups.append({
					"accountHeadId": account_head_id,
					"accountHeadAmount": account_head_amount,
					"firstYearBudget": first_year,
					"secondYearBudget": second_year,
					"thirdYearBudget": third_year,
					"fourthYearBudget": fourth_year,
					"fifthYearBudget": fifth_year
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
			"fundReceivedRefNumberFap": doc.name,  # Mapped from autoname
			"sanctionNumber": sanction_ref,  # Fund Sanction document name (different from sanctionLetterNo)
			"sanctionLetterNo": sanction_letter_no,
			"projectNumber": doc.prjreg_title,  # Link field stores project name
			"amountReceived": float(getattr(doc, 'fund_received_amt', 0) or 0),
			"iitgAccountNumber": getattr(doc, 'bank_account', None) or "",
			"depositSlipStatus": False,  # No deposit_slip_status field in Fund Received doctype
			"fundReceivedStatus": "PENDING_APPROVAL",
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



def publish_deposit_slip(doc):
	"""
	Generic publisher for all Deposit Slip types.
	Feeds to: deposit-slip-events
	"""
	try:
		if not KAFKA_AVAILABLE:
			print("⚠️ [KAFKA] Kafka module not available, skipping sync.")
			return False

		doctype = doc.doctype
		print(f"🔄 [KAFKA] Preparing payload for {doctype}: {doc.name}")

		# Helper to format dates in ISO 8601 format with T separator
		def fmt_date(d):
			if not d:
				return None
			date_str = str(d)
			return date_str.replace(' ', 'T')
		
		from frappe.utils import flt
		
		# 1. Determine Category and Field Mappings based on Doctype
		category = "RESEARCH"
		amount_field = "amount_inclusive_gst_capital"
		
		if doctype == "Research Deposit Slip":
			category = "RESEARCH"
			amount_field = "amount_inclusive_gst_capital"
		elif doctype == "Research Consultancy Deposit Slip":
			# Logic to distinguish Research vs Consultancy E if needed, or just default
			# Existing logic checked project type
			category = "CONSULTANCY_E" 
			amount_field = "amount_inclusive_gst_capital"
			if getattr(doc, "project_title", None):
				try:
					ptype = frappe.db.get_value("Project Registration", doc.project_title, "project_type")
					if ptype and "Research" in ptype and "Consultancy" not in ptype:
						category = "RESEARCH"
				except: pass
		elif doctype == "D Consultancy Deposit Slip":
			category = "D_CONSULTANCY"
			amount_field = "amount_inclusive_of_gst"
		elif doctype == "E Non Routine Deposit Slip":
			category = "E_NON_ROUTINE"
			amount_field = "amount_inclusive_of_gst"
		elif doctype == "Other Event Deposit Slip":
			category = "OTHER_EVENT"
			amount_field = "amount_inclusive_of_gst"
		elif doctype == "T Testing Deposit Slip":
			category = "T_TESTING"
			amount_field = "amount_inclusive_of_gst"

		# 2. Get Common Fields
		project_number = getattr(doc, "project_number", "") or getattr(doc, "project_title", "") or ""
		if not project_number and getattr(doc, "project_title", None):
			# Try fetching name from Project Registration if valid link
			if frappe.db.exists("Project Registration", doc.project_title):
				project_number = extract_name(doc.project_title) or doc.project_title

		# ECS Account
		ecs_ac_no = getattr(doc, "ecs_ac_no", "") or getattr(doc, "ecs_acc_no", "") or ""
		bank_name = getattr(doc, "bank", "")

		# Amounts
		grand_total = flt(getattr(doc, amount_field, 0))
		final_total = flt(getattr(doc, "total_budget", 0)) or flt(getattr(doc, "total", 0)) or grand_total
		
		# Overhead
		overhead_amt = flt(getattr(doc, "overhead_amount", 0))
		# Calculate % if not present? Or fetch generic overhead %
		overhead_pct = 0.0
		if hasattr(doc, "overhead_percentage"): overhead_pct = flt(doc.overhead_percentage)
		elif hasattr(doc, "overhead_multiplier"): overhead_pct = flt(doc.overhead_multiplier) * 100

		# 3. GST Details
		cgst_amount = flt(getattr(doc, "cgst_9", 0))
		sgst_amount = flt(getattr(doc, "sgst_9", 0))
		total_gst = flt(getattr(doc, "total_gst", 0)) or (cgst_amount + sgst_amount)
		igst_amount = flt(getattr(doc, "igst_18", 0))
		
		gst_type = "NOGST"
		if total_gst > 0:
			if cgst_amount > 0 or sgst_amount > 0:
				gst_type = "CGST_SGST"
			elif igst_amount > 0:
				gst_type = "IGST"
				if igst_amount > total_gst: total_gst = igst_amount # Corrections

		gst_details = {
			"cgstPercentage": 9.0 if cgst_amount > 0 else 0,
			"cgstAmount": cgst_amount if cgst_amount > 0 else None,
			"sgstPercentage": 9.0 if sgst_amount > 0 else 0,
			"sgstAmount": sgst_amount if sgst_amount > 0 else None,
			"igstPercentage": 18.0 if igst_amount > 0 else 0,
			"igstAmount": igst_amount if igst_amount > 0 else None,
			"totalGstAmount": total_gst
		}

		# 4. Child Tables
		ecs_dates = []
		if hasattr(doc, "ecs_dates"):
			for row in doc.ecs_dates:
				if getattr(row, "ecs_date", None):
					ecs_dates.append(fmt_date(row.ecs_date))
		
		# Credit Distributions
		pdf_list = []
		dpf_list = []
		idf_data = {"idfPercentage": 0, "idfAmount": 0}
		swf_data = {"swfPercentage": 0, "swfAmount": 0}
		stwf_data = {"stwfPercentage": 0, "stwfAmount": 0}

		if hasattr(doc, "credit_distribution"):
			for row in doc.credit_distribution:
				label = (getattr(row, 'label', '') or "").upper()
				amt = flt(getattr(row, 'amount', 0))
				pct = flt(getattr(row, 'percentage', 0) or getattr(row, 'percentage_of_overhead', 0))
				
				emp_id = getattr(row, 'employee_id', "") or getattr(row, 'emp_id', "")
				dept_id = getattr(row, 'department_id', None) or getattr(row, 'dept_id', None)
				
				if "PDF" in label or "PRINCIPAL" in label:
					pdf_list.append({"employeeId": emp_id, "departmentId": dept_id, "pdfPercentage": pct, "pdfAmount": amt})
				elif "DPF" in label or "DEPARTMENTAL" in label:
					dpf_list.append({"departmentId": dept_id, "dpfPercentage": pct, "dpfAmount": amt})
		
		# Specific static fields for some distributions if they exist on main doc
		if hasattr(doc, "idf_amount"): idf_data["idfAmount"] = flt(doc.idf_amount)
		if hasattr(doc, "staff_welfare_amount"): swf_data["swfAmount"] = flt(doc.staff_welfare_amount)
		if hasattr(doc, "student_welfare_amount"): stwf_data["stwfAmount"] = flt(doc.student_welfare_amount)


		# 5. Build Payload
		payload = {
			"projectNumber": project_number,
			"fundReceivedRefNumber": getattr(doc, "fund_received_ref_number", 0) or 0,
			"depositSlipRefNumFab": doc.name,
			"slipNumber": doc.name,
			"category": category,
			"ecsAccountNo": ecs_ac_no,
			"bankName": bank_name,
			"bmrNumber": getattr(doc, 'bmr_number', '') or "",
			"amountReceived": grand_total,
			"amountInclusiveGst": grand_total,
			"gstType": gst_type,
			"finalGstAmount": total_gst,
			"finalTotalAmount": final_total,
			"totalOverheadPercentage": overhead_pct,
			"totalOverheadAmount": overhead_amt,
			"netProjectAmount": flt(getattr(doc, "project_balance_after_gst", 0)) or flt(getattr(doc, "prj_amount", 0)),
			"depositDate": fmt_date(doc.creation),
			"createdAt": fmt_date(doc.creation),
			"updatedAt": fmt_date(doc.modified),
			"createdBy": doc.owner,
			"updatedBy": doc.modified_by,
			"status": "APPROVED",
			"ecsDates": ecs_dates,
			"gstDetails": gst_details,
			"creditDistributionSwf": swf_data,
			"creditDistributionPdf": pdf_list,
			"creditDistributionDpf": dpf_list,
			"creditDistributionIdf": idf_data,
			"creditDistributionStwf": stwf_data
		}
		
		# Wrap
		wrapped_payload = {
			"schemaVersion": "1.0",
			"eventType": f"DEPOSIT_SLIP_{category}",
			"timestamp": datetime.utcnow().isoformat(),
			"data": payload
		}

		topic = 'deposit-slip-events'
		dlq_topic = 'deposit-slip-events-dlq'
		
		print(f"📤 [KAFKA] Sending to topic: {topic}")
		
		result = publish_message(topic, wrapped_payload, doc.name, dlq_topic)
		print(f"{'✅' if result else '❌'} [KAFKA] publish_message returned: {result}")
		return result

	except Exception as e:
		error_msg = f"Error preparing Deposit Slip payload ({doc.doctype}): {str(e)}"
		print(f"❌ [KAFKA] {error_msg}")
		frappe.log_error(error_msg, "Kafka Sync Error")
		return False

def extract_name(val):
	"""Helper to extract name from a link field value if needed."""
	return val

# Alias for backward compatibility
publish_research_consultancy_deposit_slip = publish_deposit_slip



