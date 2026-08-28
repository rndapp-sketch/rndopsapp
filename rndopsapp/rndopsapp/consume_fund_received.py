import json
from kafka import KafkaConsumer
from rndopsapp.static_config import KAFKA_BOOTSTRAP_SERVERS

# Configuration (imported from centralized config)

TOPIC = 'fund-received-events'
GROUP_ID = 'rndopsapp-consumer-group-v2'

def consume_fund_received():
    print(f"=== Fund Received Consumer ===")
    print(f"Topic: {TOPIC}")
    # print(f"Group ID: {GROUP_ID}") # Not using Group ID with manual assign
    print("Listening for messages... (Press Ctrl+C to stop)")

    try:
        from kafka import KafkaConsumer, TopicPartition

        # Initialize Consumer without group_id for manual assignment
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            auto_offset_reset='earliest',
            enable_auto_commit=False # Manual assignment management
        )

        # Get partitions for the topic
        partitions = consumer.partitions_for_topic(TOPIC)
        if not partitions:
            print(f"Error: Topic {TOPIC} not found or has no partitions.")
            return

        # Assign partitions manually
        topic_partitions = [TopicPartition(TOPIC, p) for p in partitions]
        consumer.assign(topic_partitions)
        
        # Seek to beginning to read all messages
        consumer.seek_to_beginning()
        print(f"Assigned to partitions: {partitions} and seeked to beginning.")

        for message in consumer:
            print(f"\n[Partition: {message.partition}, Offset: {message.offset}] Received Fund Received:")
            print(json.dumps(message.value, indent=2))

    except KeyboardInterrupt:
        print("\nStopping consumer...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'consumer' in locals():
            consumer.close()

if __name__ == "__main__":
    consume_fund_received()
