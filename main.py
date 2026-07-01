import json
import os
import logging
import traceback

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    """
    Master Lambda Entry Point.
    Handles API Gateway Proxy, Cognito Triggers, and Error Reporting.
    """
    try:
        # 0. Intercept manual tasks (e.g. database migrations via CI/CD)
        if isinstance(event, dict) and event.get("task") == "migrate_database":
            logger.info("Executing database migration task...")
            from alembic.config import Config
            from alembic import command
            
            # The alembic.ini is in the root directory (where main.py is)
            alembic_cfg = Config("alembic.ini")
            command.upgrade(alembic_cfg, "head")
            
            logger.info("Database migration completed successfully.")
            return {"statusCode": 200, "body": "Migration successful"}

        # 1. Detect AWS Cognito Triggers (Lightweight)
        if "triggerSource" in event:
            trigger = event["triggerSource"]
            logger.info(f"Cognito Trigger: {trigger}")
            
            if trigger.startswith("PostConfirmation"):
                from services.auth.handler import post_confirmation
                return post_confirmation(event, context)
            
            if trigger.startswith("CustomMessage") or trigger.startswith("CustomEmailSender"):
                from services.auth.custom_sender import handler as custom_message_handler
                return custom_message_handler(event, context)
                
            return event # Return event unchanged if no specific handler

        # 2. API is a  Gateway Routing (FastAPI - Deferred)
        from mangum import Mangum
        from local_server import app
        
        # Apply environment-specific titles/security
        env = os.environ.get("ENV", "dev")
        app.title = f"KapuLetu Treasury API ({env.capitalize()})"
        if env == "prod":
            app.docs_url = None
            app.redoc_url = None

        handler_func = Mangum(app, lifespan="off")
        return handler_func(event, context)

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"RUNTIME ERROR: {error_trace}")
        
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "error": "lambda_runtime_error",
                "message": str(e),
                "traceback": error_trace
            })
        }
