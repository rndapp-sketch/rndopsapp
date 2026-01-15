
import frappe
import sys
import logging
from rndopsapp.rndopsapp.kafka_consumer import start_consumer_loop, get_consumer, KAFKA_AVAILABLE, close_consumer

# Configure logging to stdout
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

def run():
    print("=== DEBUG: Foreground Consumer Runner ===")
    print(f"KAFKA_AVAILABLE: {KAFKA_AVAILABLE}")
    
    if not KAFKA_AVAILABLE:
        print("ERROR: Kafka library not available")
        return

    print("Closing any existing consumer...")
    close_consumer()
    
    print("Initializing consumer...")
    consumer = get_consumer()
    if consumer:
        print("Consumer initialized successfully.")
        print(f"Subscription: {consumer.subscription()}")
    else:
        print("Failed to initialize consumer.")
        return

    # print("Checking unconsumed offset 0...")
    # try:
    #     check_unconsumed_offset_zero()
    #     print("check_unconsumed_offset_zero completed.")
    # except Exception as e:
    #     print(f"Error in check_unconsumed_offset_zero: {e}")

    print("Starting consumer loop...")
    start_consumer_loop()

if __name__ == "__main__":
    run()
