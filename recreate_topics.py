import time
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import UnknownTopicOrPartitionError

BOOTSTRAP_SERVERS = ['172.16.135.118:9095', '172.16.135.118:9096']
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

def recreate_topics():
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP_SERVERS, client_id='topic-recreator')
    
    # Check what exists currently
    existing = admin.list_topics()
    print(f"Existing topics on broker: {existing}")

    # Identify missing topics or topics we intend to manage
    missing_topics = [t for t in TOPICS if t not in existing]
    
    # If a topic is "marked for deletion", it might NOT show up in list_topics() depending on the broker version/state,
    # OR it might show up. Verification is tricky. 
    # But usually if we try to create and it says "TopicAlreadyExists", it means it's there.
    # If it says "marked for deletion", it means it's dying.
    
    # We will try to create ALL TOPICS in the list.
    # checking list_topics is good, but "marked for deletion" topics sometimes disappear from list_topics before they are mostly gone.
    # So we will try to create anything we don't see, AND handle errors.
    
    topics_to_create_names = TOPICS # We want to ensure ALL these exist with correct config. 
    # Since we can't easily check config, we assume if it exists now, it's either the old one (if delete failed?) or the new one.
    # Given we just ran delete, existing ones are likely new (good) or old (stuck).
    # Let's filter by missing to be safe against double-creating good ones.
    
    topics_to_attempt = [t for t in TOPICS if t not in existing]
    if not topics_to_attempt:
        print("All topics seem to exist. (If config is wrong, you must delete manually).")
        # We might have some topics that are 'marked for deletion' but still show in list_topics? 
        # Typically list_topics hides them. So if they are in existing, they are likely good or zombie.
        # Let's verify creation for "missing" ones.
    
    print(f"Attempting to create: {topics_to_attempt}")
    
    if not topics_to_attempt:
        return

    new_topics = [
        NewTopic(name=t, num_partitions=NUM_PARTITIONS, replication_factor=REPLICATION_FACTOR)
        for t in topics_to_attempt
    ]
    
    # Retry creation logic to handle "marked for deletion" race conditions
    creation_retries = 20
    while creation_retries > 0:
        try:
            if not new_topics:
                print("No topics left to create.")
                break

            val = admin.create_topics(new_topics)
            print("Topics created successfully.")
            break
        except Exception as e:
            msg = str(e)
            print(f"Creation attempt failed: {e}")
            
            if "marked for deletion" in msg:
                 print("Waiting for topics to finish deletion... (5s)")
                 time.sleep(5)
                 creation_retries -= 1
            elif "TopicAlreadyExistsError" in msg:
                # Some might have succeeded in a partial batch, or exist now.
                # Refetch existing and update list
                time.sleep(2)
                current_existing = admin.list_topics()
                
                # Filter new_topics to only those that are NOT in current_existing
                new_topics = [nt for nt in new_topics if nt.name not in current_existing]
                
                if not new_topics:
                    print("All topics now exist!")
                    break
                print(f"Retrying for remaining: {[nt.name for nt in new_topics]}")
            else:
                # Unknown error
                print("Unknown error, retrying...")
                time.sleep(5)
                creation_retries -= 1
    
    if creation_retries == 0:
        print("Failed to create topics after multiple retries.")
            
    try:
        admin.close()
    except:
        pass

if __name__ == "__main__":
    recreate_topics()
