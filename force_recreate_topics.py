import time
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import UnknownTopicOrPartitionError

BOOTSTRAP_SERVERS = ['172.16.134.81:9095', '172.16.134.81:9096']
NUM_PARTITIONS = 2
REPLICATION_FACTOR = 2

TOPICS = [
    'fund-received-events',
    'fund-sanction-events',
    'deposit-slip-events',
    'account-head-commit-events',
    'account-head-payment-events',
    'project-registration-events',
    'fund-received-events-dlq',
    'fund-sanction-events-dlq',
    'project-registration-events-dlq'
]

def force_recreate_topics():
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP_SERVERS, client_id='topic-recreator-force')
    
    print("FORCE DELETE MODE")
    print(f"Deleting topics: {TOPICS}")
    try:
        admin.delete_topics(TOPICS)
    except UnknownTopicOrPartitionError:
        print("Some topics didn't exist, continuing...")
    except Exception as e:
        print(f"Delete request error (might already be deleting): {e}")

    print("Waiting for topics to be fully deleted (polling list_topics)...")
    deletion_wait_retries = 30
    while deletion_wait_retries > 0:
        existing = admin.list_topics()
        remaining = [t for t in TOPICS if t in existing]
        if not remaining:
            print("All topics confirmed deleted.")
            break
        print(f"Still waiting for deletion of: {remaining}")
        time.sleep(2)
        deletion_wait_retries -= 1
    
    if deletion_wait_retries == 0:
        print("Timed out waiting for deletion. Broker might be slow/stuck. Proceeding to creation anyway (might fail)...")

    print("Creating topics...")
    new_topics = [
        NewTopic(name=t, num_partitions=NUM_PARTITIONS, replication_factor=REPLICATION_FACTOR)
        for t in TOPICS
    ]
    
    # Retry creation logic to handle "marked for deletion" race conditions
    creation_retries = 20
    while creation_retries > 0:
        try:
            # We want to create ALL of them. 
            # If some exist now (race condition), filtering them out is tricky without knowing their config.
            # But since we just deleted, any that exist are likely zombie/stuck.
            # We blindly try to create. 
            
            # Check what's missing again explicitly to avoid partial failures
            curr_existing = admin.list_topics()
            to_create = [nt for nt in new_topics if nt.name not in curr_existing]
            
            if not to_create:
                print("All topics created/exist!")
                break
                
            print(f"Attempting batch creation for: {[nt.name for nt in to_create]}")
            admin.create_topics(to_create)
            print("Batch creation successful.")
            break

        except Exception as e:
            msg = str(e)
            print(f"Creation attempt failed: {e}")
            
            if "marked for deletion" in msg:
                 print("Waiting for topics to finish deletion... (5s)")
                 time.sleep(5)
                 creation_retries -= 1
            elif "TopicAlreadyExistsError" in msg:
                print("TopicAlreadyExists encountered, retrying remaining...")
                time.sleep(2)
                # Loop will re-check existing and filter
            else:
                print("Unknown error, retrying...")
                time.sleep(5)
                creation_retries -= 1
    
    if creation_retries == 0:
        print("Failed to ensure topics after multiple retries.")
            
    try:
        admin.close()
    except:
        pass

if __name__ == "__main__":
    force_recreate_topics()
