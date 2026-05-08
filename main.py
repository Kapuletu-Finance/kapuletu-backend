import json
import os
import logging
import traceback

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

try:
    from mangum import Mangum
    from local_server import app
    
    # This is the entry point for AWS Lambda
    handler = Mangum(app, lifespan="off")
    logger.info("Successfully initialized Mangum and FastAPI app")

except Exception as e:
    # If the app fails to even START (e.g. missing dependency), 
    # we catch it here so it doesn't just show "Internal Server Error"
    error_trace = traceback.format_exc()
    logger.error(f"FAILED TO INITIALIZE APP: {error_trace}")
    
    def handler(event, context):
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "error": "initialization_failed",
                "message": str(e),
                "traceback": error_trace
            })
        }

# --- Environment Info for the Landing Page ---
if os.environ.get("ENV") == "dev":
    app.title = "KapuLetu Treasury API (Development)"
elif os.environ.get("ENV") == "prod":
    app.title = "KapuLetu Treasury API (Production)"
    app.docs_url = None
    app.redoc_url = None
