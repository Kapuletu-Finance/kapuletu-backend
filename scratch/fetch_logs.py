import boto3
from datetime import datetime, timedelta

def fetch_logs():
    client = boto3.client('logs', region_name='eu-west-1')
    log_group = '/aws/lambda/kapuletu-dev-backend'
    
    start_time = int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000)
    
    try:
        response = client.filter_log_events(
            logGroupName=log_group,
            startTime=start_time,
            limit=50,
            interleaved=True
        )
        for event in response.get('events', []):
            print(event['message'].strip())
    except Exception as e:
        print(f"Error fetching logs: {e}")

if __name__ == "__main__":
    fetch_logs()
