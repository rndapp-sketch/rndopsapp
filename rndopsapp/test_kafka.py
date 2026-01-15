import sys
import os

# Add bench path to sys.path to import frappe if needed, 
# but for this standalone test we just need kafka-python
try:
    from kafka import KafkaProducer
    import json
    
    print("kafka-python imported successfully")
    
    KAFKA_BOOTSTRAP_SERVERS = [
        '172.16.135.118:9095',
        '172.16.135.118:9096',
        '172.16.135.118:9097'
    ]
    
    print(f"Connecting to: {KAFKA_BOOTSTRAP_SERVERS}")
    
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        request_timeout_ms=5000
    )
    
    print("Producer initialized")
    
    topic = 'project-registration-events'
    payload = {"test": "message", "source": "frappe-verification-script"}
    
    print(f"Sending message to {topic}...")
    future = producer.send(topic, payload)
    result = future.get(timeout=10)
    
    print(f"Message sent! Partition: {result.partition}, Offset: {result.offset}")
    producer.close()
    
except Exception as e:
    print(f"Error: {e}")



#  /home/prornd/project/frappe_dev/prornd/env/bin/python test_kafka_dummy_data.py