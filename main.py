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
        # 1. Intercept SQS Events (Webhook Background Processing)
        if isinstance(event, dict) and "Records" in event:
            record = event["Records"][0]
            if record.get("eventSource") == "aws:sqs":
                logger.info("Processing SQS Event for Ingestion")
                from services.ingestion.handler import process_sqs_record
                result = process_sqs_record(record)
                return result

        # 2. Intercept manual tasks (e.g. database migrations via CI/CD)
        if isinstance(event, dict) and event.get("task") == "migrate_database":
            logger.info("Executing database migration task...")
            from alembic.config import Config
            from alembic import command
            from sqlalchemy import create_engine, text, inspect
            from common.config import get_config
                
            alembic_cfg = Config("alembic.ini")
            
            # Self-healing logic for databases created by auto-migration
            try:
                engine = create_engine(get_config().DATABASE_URL)
                inspector = inspect(engine)
                has_tables = inspector.has_table("users")
                
                current_rev = None
                if inspector.has_table("alembic_version"):
                    with engine.connect() as conn:
                        current_rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                        
                if has_tables and not current_rev:
                    logger.warning("Database has tables but no alembic version! Stamping to e291751da8fb...")
                    command.stamp(alembic_cfg, "e291751da8fb")
            except Exception as e:
                logger.error(f"Failed during self-healing check: {e}")
                return {
                    "statusCode": 500,
                    "body": json.dumps({"error": "self_healing_failed", "message": str(e), "traceback": traceback.format_exc()})
                }
                
            try:
                command.upgrade(alembic_cfg, "head")
            except Exception as e:
                return {
                    "statusCode": 500,
                    "body": json.dumps({"error": "migration_upgrade_failed", "message": str(e), "traceback": traceback.format_exc()})
                }
            
            logger.info("Database migration completed successfully.")
            return {"statusCode": 200, "body": "Migration successful"}
            
        # 3. Intercept seeding tasks
        if isinstance(event, dict) and event.get("task") == "seed_plans":
            logger.info("Executing seed plans task...")
            try:
                from scripts.seed_plans import seed_plans
                seed_plans()
                logger.info("Seed plans completed successfully.")
                return {"statusCode": 200, "body": "Seed successful"}
            except Exception as e:
                return {
                    "statusCode": 500,
                    "body": json.dumps({"error": "seed_failed", "message": str(e), "traceback": traceback.format_exc()})
                }

        # 4. API is a Gateway Routing (FastAPI - Deferred)
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
