import time
from typing import Any, Optional
from sqlalchemy.orm import Session
from models.system_config import SystemConfig

# Simple in-memory cache
_CONFIG_CACHE = {}
_CACHE_TTL = 30  # seconds

def get_system_config(db: Session, key: str, default: Any = None) -> Any:
    """
    Retrieves a configuration value by key, using an in-memory TTL cache
    to avoid flooding the database on every middleware/request cycle.
    """
    current_time = time.time()
    
    # Check cache first
    if key in _CONFIG_CACHE:
        cached_value, timestamp = _CONFIG_CACHE[key]
        if current_time - timestamp < _CACHE_TTL:
            return cached_value
            
    # Cache miss or expired, fetch from DB
    config = db.query(SystemConfig).filter(SystemConfig.config_key == key).first()
    value = config.config_value if config else default
    
    # Update cache
    _CONFIG_CACHE[key] = (value, current_time)
    
    return value
