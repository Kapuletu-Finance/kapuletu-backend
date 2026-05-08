import os
from mangum import Mangum
from local_server import app

# This is the entry point for AWS Lambda (Proxy Integration)
# Mangum takes the FastAPI 'app' and makes it work with AWS events
handler = Mangum(app, lifespan="off")

# We can also add environment-specific logic here if needed
if os.environ.get("ENV") == "dev":
    app.title = "KapuLetu Treasury API (Development)"
elif os.environ.get("ENV") == "prod":
    app.title = "KapuLetu Treasury API (Production)"
    app.docs_url = None # Disable Swagger UI in production for security
    app.redoc_url = None
