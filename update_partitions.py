from kafka.admin import KafkaAdminClient, NewPartitions
from kafka.errors import KafkaError

BOOTSTRAP_SERVERS = ['172.16.134.81:9095', '172.16.134.81:9096']
TOPICS_TO_UPDATE = [
    'fund-received-events',
    'fund-sanction-events',
    'deposit-slip-events',
    'account-head-commit-events',
    'account-head-payment-events',
    'project-registration-events'
]
TARGET_PARTITIONS = 2

def increase_partitions():
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=BOOTSTRAP_SERVERS,
            client_id='partition-updater'
        )
        
        topic_partitions = {}
        for topic in TOPICS_TO_UPDATE:
            topic_partitions[topic] = NewPartitions(total_count=TARGET_PARTITIONS)
            
        print(f"Attempting to increase partitions to {TARGET_PARTITIONS} for: {TOPICS_TO_UPDATE}")
        
        admin_client.create_partitions(topic_partitions)
        print("Successfully requested partition increase.")
        
    except Exception as e:
        print(f"Error updating partitions: {e}")
    finally:
        try:
            admin_client.close()
        except:
            pass

if __name__ == "__main__":
    increase_partitions()
