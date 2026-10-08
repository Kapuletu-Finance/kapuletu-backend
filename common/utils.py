import datetime
import math
import re
import uuid
from zoneinfo import ZoneInfo

# Kapuletu operates on East Africa Time; business-day boundaries use this zone.
NAIROBI_TZ = ZoneInfo("Africa/Nairobi")

def parse_uuid(value) -> uuid.UUID:
    """
    Safely convert a string, UUID, or any value to a uuid.UUID object.
    Use this before passing any user-supplied ID into a SQLAlchemy UUID column.
    """
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as e:
        raise ValueError(f"Invalid UUID: {value!r}") from e


def generate_slug(text: str) -> str:
    """Generates a URL-friendly slug from a given string."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def format_currency(amount):
    """
    Converts a numeric amount into a standardized Kenyan Shillings currency string.
    
    Args:
        amount (float or int): The monetary value.
        
    Returns:
        str: Formatted string (e.g., "KES 1,250.00").
    """
    return f"KES {amount:,.2f}"

def generate_id():
    """
    Generates a unique identifier using UUID4.
    
    Returns:
        str: A version 4 Universally Unique Identifier.
    """
    return str(uuid.uuid4())


def nairobi_now() -> datetime.datetime:
    """Current time as a timezone-aware datetime in Africa/Nairobi."""
    return datetime.datetime.now(NAIROBI_TZ)


def nairobi_today() -> datetime.date:
    """Today's calendar date in Africa/Nairobi (not UTC)."""
    return nairobi_now().date()


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle (haversine) distance between two GPS points, in meters."""
    earth_radius_m = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return earth_radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
