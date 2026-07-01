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
            from sqlalchemy import create_engine, text
            from common.config import get_config
            
            alembic_cfg = Config("alembic.ini")
            
            # Self-healing logic for databases created by auto-migration
            try:
                engine = create_engine(get_config().DATABASE_URL)
                with engine.connect() as conn:
                    has_tables = conn.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name = 'users'")).scalar()
                    try:
                        current_rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                    except Exception:
                        current_rev = None
                        
                if has_tables and not current_rev:
                    logger.warning("Database has tables but no alembic version! Stamping to e291751da8fb...")
                    command.stamp(alembic_cfg, "e291751da8fb")
            except Exception as e:
                logger.error(f"Failed during self-healing check: {e}")
                
            command.upgrade(alembic_cfg, "head")
            
            logger.info("Database migration completed successfully.")
            return {"statusCode": 200, "body": "Migration successful"}

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
