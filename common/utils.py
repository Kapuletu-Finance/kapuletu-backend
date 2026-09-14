import uuid
import re

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
