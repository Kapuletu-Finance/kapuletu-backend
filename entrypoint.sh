#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "Running Database Migrations..."
alembic upgrade head

echo "Running Database Seeding..."
# This is safe because seed_plans.py skips existing plans
python scripts/seed_plans.py

echo "Starting the application..."
# Execute the CMD from the Dockerfile
exec "$@"
