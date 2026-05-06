from dataclasses import dataclass

@dataclass
class Member:
    """
    Member Dataclass: A lightweight representation of a community group member.
    
    Used for transferring member data between service layers and API responses. --This model is to be implemented in futuee not now
    """
    # Unique identifier for the member
    id: str
    # Full name of the member
    name: str
    # Primary contact number
    phone: str
    # ISO timestamp when the member joined the group
    joined_at: str
