import os
from celery import Celery

# Redis URL for Celery Broker and Backend. 
# We default to local Redis if env variables are not present.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "kapuletu_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["services.notifications.tasks"]
)

# Optional configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Nairobi",
    enable_utc=True,
)
