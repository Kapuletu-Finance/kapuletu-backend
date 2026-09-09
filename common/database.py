from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.config import get_config

# Database Configuration & Session Management
# This module provides the central database interface for the entire KapuLetu Backend.

config = get_config()

# SQLAlchemy Engine Initialization
# We use pooled connections to optimize performance, but with a small pool size
# to accommodate the high-concurrency, short-lived nature of AWS Lambda.
is_sqlite = config.DATABASE_URL.startswith("sqlite")

engine_kwargs = {}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10
    if config.DB_SSL_REQUIRED:
        engine_kwargs["connect_args"] = {"sslmode": "require"}

engine = create_engine(
    config.DATABASE_URL,
    **engine_kwargs
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
