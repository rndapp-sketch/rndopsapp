import time
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import UnknownTopicOrPartitionError

BOOTSTRAP_SERVERS = ['172.16.134.81:9095', '172.16.134.81:9096']
NUM_PARTITIONS = 2
REPLICATION_FACTOR = 2

# Targeted list of topics that failed to update
TOPICS = [
    'deposit-slip-events',
    'account-head-commit-events',
    'account-head-payment-events'
]

def fix_remaining_topics():
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP_SERVERS, client_id='topic-fixer')
    
    print(f"Fixing specific topics: {TOPICS}")
    
    # 1. DELETE
    print("Step 1: Deleting...")
    try:
        admin.delete_topics(TOPICS)
    except UnknownTopicOrPartitionError:
        print("Topics didn't exist, moving to creation.")
    except Exception as e:
        print(f"Delete warning: {e}")

    # 2. WAIT FOR DELETION
    print("Step 2: Waiting for deletion...")
    wait_retries = 30
    while wait_retries > 0:
        existing = admin.list_topics()
        remaining = [t for t in TOPICS if t in existing]
        if not remaining:
            print("Confirmed: Topics are gone.")
            break
        print(f"Still waiting for: {remaining}...")
        time.sleep(2)
        wait_retries -= 1
    
    # 3. CREATE
    print("Step 3: Creating with correct config...")
    new_topics = [
        NewTopic(name=t, num_partitions=NUM_PARTITIONS, replication_factor=REPLICATION_FACTOR)
        for t in TOPICS
    ]
    
    created = False
    create_retries = 20
    while create_retries > 0:
        try:
            # check if they exist again (race condition from other apps)
            existing = admin.list_topics()
            topic_objects_to_create = [nt for nt in new_topics if nt.name not in existing]
            
            if not topic_objects_to_create:
                print("All target topics exist now.")
                created = True
                break

            admin.create_topics(topic_objects_to_create)
            print("Creation successful.")
            created = True
            break
        except Exception as e:
            msg = str(e)
            if "marked for deletion" in msg:
                print("Waiting for deletion cleanup...")
                time.sleep(3)
            elif "TopicAlreadyExistsError" in msg:
                print("Race condition: Topic created by something else? Retrying check...")
                time.sleep(2)
            else:
                print(f"Error: {e}")
                time.sleep(2)
            create_retries -= 1
            
    if created:
        print("\nDONE. Please check UI.")
    else:
        print("\nFAILED to clean up and recreate some topics.")

    admin.close()

if __name__ == "__main__":
    fix_remaining_topics()
