from sqlalchemy import Column, String, UUID

from .base import Base

class Group(Base):
    """
    Group Model: Represents a community organization or Chamas.
    
    This is the primary organizational unit in KapuLetu. 
    A treasurer can manage multiple groups, each with its own members,
    campaigns, and financial history.
    """
    __tablename__ = "groups"

    # Unique identifier for the group
    group_id = Column(UUID, primary_key=True)
    # The treasurer who owns/manages this group
    owner_id = Column(UUID)
    # The name of the group (e.g. 'St. Peters Welfare')
    group_name = Column(String)
    # Primary currency used for this group's transactions (Default: KES)
    currency = Column(String)