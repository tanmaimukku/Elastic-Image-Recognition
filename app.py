#Load the AWS SDK
import boto3
print("1. AWS SDK loaded, boto3 for Python")
import time
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()
print("2. Environment variables (Access information) loaded from .env file")

# Initialize AWS clients
region = 'us-east-2'  

ec2 = boto3.resource('ec2', region_name=region)
s3 = boto3.client('s3', region_name=region)
s3_resource = boto3.resource('s3', region_name=region)
sqs = boto3.client('sqs', region_name=region)

key_pair_name = 'tanmaimukku_key_pair'

existing_key_pairs = [kp.name for kp in ec2.key_pairs.all()]
if key_pair_name not in existing_key_pairs:
    key_pair = ec2.create_key_pair(KeyName=key_pair_name)
    # Save the private key to a .pem file
    with open(f'{key_pair_name}.pem', 'w') as file:
        file.write(key_pair.key_material)
    print(f"Key pair '{key_pair_name}' created and saved.")
else:
    print(f"Key pair '{key_pair_name}' already exists.")

images = ec2.meta.client.describe_images(
    Owners=['099720109477'],  
    Filters=[
        {'Name': 'name', 'Values': ['ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*']},
        {'Name': 'state', 'Values': ['available']},
        {'Name': 'root-device-type', 'Values': ['ebs']},
        {'Name': 'virtualization-type', 'Values': ['hvm']},
    ]
)

# Sort images by CreationDate descending
images = sorted(images['Images'], key=lambda x: x['CreationDate'], reverse=True)
ami_id = images[0]['ImageId']
print(f"Latest Ubuntu AMI ID: {ami_id}")

instances = ec2.create_instances(
    ImageId=ami_id,
    MinCount=1,
    MaxCount=1,
    InstanceType='t2.micro',
    KeyName=key_pair_name
)

instance = instances[0]
print(f"EC2 instance '{instance.id}' is launching.")

import uuid
bucket_name = f'tanmaimukku-bucket-{uuid.uuid4()}'
print(f"S3 bucket name: {bucket_name}")

s3.create_bucket(
    Bucket=bucket_name,
    CreateBucketConfiguration={'LocationConstraint': region}
)
print(f"S3 bucket '{bucket_name}' created.")

queue_name = 'tanmaimukku-queue.fifo'

response = sqs.create_queue(
    QueueName=queue_name,
    Attributes={
        'FifoQueue': 'true',
        'ContentBasedDeduplication': 'true'
    }
)

queue_url = response['QueueUrl']
print(f"SQS FIFO queue '{queue_name}' created with URL: {queue_url}")

print("3. AWS clients initialized (sent resource request API calls to AWS to create the EC2 instance, S3 bucket, and SQS queue.)")

print("4. Request sent, waiting for 1 minute...")
time.sleep(60)

print("5. Listing all EC2 instances, S3 buckets, and SQS queues in in the current region")

print("\nListing EC2 Instances:")
for instance in ec2.instances.all():
    print(f"- Instance ID: {instance.id}, State: {instance.state['Name']}")

print("\nListing S3 Buckets:")
response = s3.list_buckets()
for bucket in response['Buckets']:
    print(f"- {bucket['Name']}")

print("\nListing SQS Queues:")
response = sqs.list_queues(QueueNamePrefix='tanmaimukku')
if 'QueueUrls' in response:
    for url in response['QueueUrls']:
        print(f"- {url}")
else:
    print("No SQS queues found.")

print("\n6. Creating an empty file and uploading it to the S3 bucket")

file_name = 'CSE546test.txt'
with open(file_name, 'w') as file:
    file.write('')  # Empty content
print(f"Empty file '{file_name}' created.")

s3.upload_file(file_name, bucket_name, file_name)
print(f"File '{file_name}' uploaded to S3 bucket '{bucket_name}'.")

print("7. Sending a test message to the SQS queue")

message_name = 'test message'
message_body = 'This is a test message'
response = sqs.send_message(
    QueueUrl=queue_url,
    MessageBody=message_body,
    MessageGroupId='messageGroup1',  # Required for FIFO queues
    MessageAttributes={
        'Name': {
            'DataType': 'String',
            'StringValue': message_name
        }
    }
)
print("Message sent to SQS queue.")

attributes = sqs.get_queue_attributes(
    QueueUrl=queue_url,
    AttributeNames=['ApproximateNumberOfMessages']
)
message_count = attributes['Attributes']['ApproximateNumberOfMessages']
print(f"8. Number of messages in queue: {message_count}")

response = sqs.receive_message(
    QueueUrl=queue_url,
    MaxNumberOfMessages=1,
    MessageAttributeNames=['All'],
    WaitTimeSeconds=0
)

if 'Messages' in response:
    message = response['Messages'][0]
    print("9. Pulling message from SQS queue:")
    print(f"Name: {message['MessageAttributes']['Name']['StringValue']}")
    print(f"Body: {message['Body']}")
    
    # Delete the message from the queue
    sqs.delete_message(
        QueueUrl=queue_url,
        ReceiptHandle=message['ReceiptHandle']
    )
    print("Message deleted from queue.")
else:
    print("No messages received.")

attributes = sqs.get_queue_attributes(
    QueueUrl=queue_url,
    AttributeNames=['ApproximateNumberOfMessages']
)
message_count = attributes['Attributes']['ApproximateNumberOfMessages']
print(f"10. Number of messages in queue after pulling: {message_count}")

print("11. Waiting for 10 seconds...")
time.sleep(10)

print("12. Deleting all EC2 instances, S3 buckets, and SQS queues in the current region")

# Delete all EC2 instances
print("\nTerminating all EC2 instances...")
all_instances = list(ec2.instances.all())
instance_ids = [instance.id for instance in all_instances]

if instance_ids:
    for instance_id in instance_ids:
        instance = ec2.Instance(instance_id)
        instance.terminate()
        print(f"Termination initiated for EC2 instance '{instance_id}'.")
    # Wait for all instances to terminate
    for instance_id in instance_ids:
        instance = ec2.Instance(instance_id)
        instance.wait_until_terminated()
        print(f"EC2 instance '{instance_id}' terminated.")
else:
    print("No EC2 instances found to terminate.")

# Delete all S3 buckets
print("\nDeleting all S3 buckets...")
buckets = s3_resource.buckets.all()
bucket_names = [bucket.name for bucket in buckets]

if bucket_names:
    for b_name in bucket_names:
        bucket = s3_resource.Bucket(b_name)
        print(f"Deleting objects in S3 bucket '{b_name}'...")
        bucket.objects.all().delete()
        print(f"Deleting S3 bucket '{b_name}'...")
        try:
            bucket.delete()
            print(f"S3 bucket '{b_name}' deleted.")
        except Exception as e:
            print(f"Error deleting bucket '{b_name}': {e}")
else:
    print("No S3 buckets found to delete.")

# Delete all SQS queues
print("\nDeleting all SQS queues...")
response = sqs.list_queues()
queue_urls = response.get('QueueUrls', [])

if queue_urls:
    for q_url in queue_urls:
        sqs.delete_queue(QueueUrl=q_url)
        print(f"SQS queue '{q_url}' deleted.")
else:
    print("No SQS queues found to delete.")

print("13. Waiting for 20 seconds...")
time.sleep(20)

print("14. Listing all EC2 instances, S3 buckets, and SQS queues in the current region after deletion")

print("\nListing EC2 Instances after deletion:")
for inst in ec2.instances.all():
    print(f"- Instance ID: {inst.id}, State: {inst.state['Name']}")

print("\nListing S3 Buckets after deletion:")
response = s3.list_buckets()
for bucket in response['Buckets']:
    print(f"- {bucket['Name']}")

print("\nListing SQS Queues after deletion:")
response = sqs.list_queues()
if 'QueueUrls' in response and response['QueueUrls']:
    for url in response['QueueUrls']:
        print(f"- {url}")
else:
    print("No SQS queues found.")


