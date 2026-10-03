import datetime
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from .base import Base


class BlogPost(Base):
    """
    BlogPost Model: Represents a blog post or news article.
    """
    __tablename__ = "blog_posts"

    # Unique identifier for the blog post
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    slug = Column(String(255), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    excerpt = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    cover_image_url = Column(String(1024), nullable=True)
    
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    author_name = Column(String(255), nullable=True)
    author_role = Column(String(255), nullable=True)
    
    category = Column(String(100), nullable=True)
    
    is_published = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
