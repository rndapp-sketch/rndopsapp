import json
from datetime import datetime
from kafka import KafkaProducer
from project_event_dto import ProjectEventDTO, ProjectDataDTO

# --- CONFIGURATION ---
KAFKA_BOOTSTRAP_SERVERS = [
    '172.16.135.118:9095',
    '172.16.135.118:9096',
    '172.16.135.118:9097'
]

TOPIC_PROJECT = 'project-registration-events'
SCHEMA_VERSION = '1.0'


def get_producer():
    """Create and return a Kafka producer."""
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks="all",
            retries=3,
            linger_ms=10
        )
        return producer
    except Exception as e:
        print(f"❌ Failed to connect to Kafka: {e}")
        return None


def test_dummy_data():
    print("=== Starting Standalone Dummy Data Test for Kafka Sync ===")
    
    # Get Kafka producer
    producer = get_producer()
    if not producer:
        print("❌ Cannot proceed without Kafka connection")
        return
    
    print(f"✅ Connected to Kafka brokers: {KAFKA_BOOTSTRAP_SERVERS}")
    
    # ---------------------------------------------------------
    # Test Project Registration with provided data
    # ---------------------------------------------------------
    print("\n[1] Testing Project Registration Sync...")
    
    try:
        # Build ProjectDataDTO with the exact data provided
        project_data = ProjectDataDTO(
            projectNumber="2026010201MeiTy000195",
            empId="391",
            departmentId="1",
            projectType="Research",
            projectCategory="",
            fundingAgencyType="Government",
            fundingAgencyId="MeiTy",
            projectScheme="",
            totalBudgetAmount=64579496.0,
            overHeadAmountPercentage=15.0,
            overHeadAmount=0.0,
            budgetWithOverHeadAmount=0.0,
            gst=0.0,
            grandTotal=0.0,
            startDate=None,
            completionDate=None,
            durationMonths=24,
            status="Approved",
            applyDate=datetime.fromisoformat("2026-01-02T15:00:50.315588"),
            implementedDeptCentres=[]
        )

        # Build ProjectEventDTO
        event = ProjectEventDTO(
            schemaVersion=SCHEMA_VERSION,
            eventType="PROJECT_REGISTRATION",
            timestamp=datetime.fromisoformat("2026-01-02T09:39:07.313140"),
            data=project_data
        )

        # Convert to dict for Kafka serialization
        payload = event.model_dump(mode="json")
        
        print("Payload to publish:")
        print(json.dumps(payload, indent=2))
        
        # Send to Kafka
        future = producer.send(TOPIC_PROJECT, payload)
        record_metadata = future.get(timeout=10)
        
        print(f"✅ Project Registration sent successfully!")
        print(f"   Topic: {record_metadata.topic}")
        print(f"   Partition: {record_metadata.partition}")
        print(f"   Offset: {record_metadata.offset}")
        
    except Exception as e:
        print(f"❌ Project Registration failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Close producer
    producer.flush()
    producer.close()
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_dummy_data()
