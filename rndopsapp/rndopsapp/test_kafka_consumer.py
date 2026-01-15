import sys
import json
from kafka import KafkaConsumer

# Configuration
KAFKA_BOOTSTRAP_SERVERS = [
    '172.16.135.118:9095',
    '172.16.135.118:9096',

]

TOPICS = [
    'project-registration-events',
    'fund-sanction-events',
    'fund-received-events'
]

def test_consumer():
    print("=== Starting Kafka Consumer Test ===")
    print(f"Connecting to: {KAFKA_BOOTSTRAP_SERVERS}")
    print(f"Subscribing to topics: {TOPICS}")

    try:
        consumer = KafkaConsumer(
            *TOPICS,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            auto_offset_reset='earliest', # Start from beginning to pick up previous test messages
            enable_auto_commit=False,     # Don't commit offsets so we can re-run test
            group_id='test-consumer-group-v1', # Unique group to ensure isolation if needed
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            consumer_timeout_ms=5000      # Stop after 5 seconds of silence
        )

        print("\nListening for messages (timeout 5s)...")
        
        msg_count = 0
        for message in consumer:
            msg_count += 1
            print(f"\n[Topic: {message.topic}] [Partition: {message.partition}] [Offset: {message.offset}]")
            print(f"Key: {message.key}")
            print(f"Value: {json.dumps(message.value, indent=2)}")

        if msg_count == 0:
            print("\n⚠️ No messages found. Did you run the producer test first?")
        else:
            print(f"\n✅ Successfully consumed {msg_count} messages.")

    except Exception as e:
        print(f"\n❌ Consumer failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n=== Consumer Test Complete ===")

if __name__ == "__main__":
    test_consumer()
