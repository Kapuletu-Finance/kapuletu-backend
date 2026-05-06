import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from common.config import get_config

# Database Configuration & Session Management
# This module provides the central database interface for the entire KapuLetu Backend.

config = get_config()

# SQLAlchemy Engine Initialization
# We use pooled connections to optimize performance, but with a small pool size
# to accommodate the high-concurrency, short-lived nature of AWS Lambda.
engine = create_engine(
    config.DATABASE_URL,
    # pool_size: The number of connections to keep open in the pool.
    pool_size=5,
    # max_overflow: The number of additional connections that can be created if the pool is full.
    max_overflow=10,
    # SSL is required for production RDS instances but disabled for local development.
    connect_args={"sslmode": "require"} if all(h not in config.DATABASE_URL for h in ["localhost", "127.0.0.1"]) else {}
)

# SessionLocal is the factory for individual database sessions.
# - autocommit=False: Transactions must be explicitly committed (Best Practice).
# - autoflush=False: Prevents premature DB writes before explicit commit calls.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    Dependency injection helper for FastAPI or internal service calls.
    Provides a database session that is automatically closed after use.
    
    Usage:
        db = next(get_db())
        # ... perform db operations ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        # Crucial for preventing connection exhaustion in Lambda
        db.close()
