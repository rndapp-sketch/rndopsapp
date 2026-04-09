import json
from kafka import KafkaConsumer

# Configuration
KAFKA_BOOTSTRAP_SERVERS = [
    '172.16.134.81:9095',
    '172.16.134.81:9096',
    '172.16.135.118:9097'
]

TOPIC = 'fund-sanction-events'
GROUP_ID = 'fund-sanction-consumer-group'

def consume_fund_sanction():
    print(f"=== Fund Sanction Consumer ===")
    print(f"Topic: {TOPIC}")
    print(f"Group ID: {GROUP_ID}")
    print("Listening for messages... (Press Ctrl+C to stop)")

    try:
        consumer = KafkaConsumer(
            TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id=GROUP_ID,
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )

        for message in consumer:
            print(f"\n[Offset: {message.offset}] Received Fund Sanction:")
            print(json.dumps(message.value, indent=2))

    except KeyboardInterrupt:
        print("\nStopping consumer...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'consumer' in locals():
            consumer.close()

if __name__ == "__main__":
    consume_fund_sanction()
