import datetime
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, Integer, JSON
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
    tags = Column(JSON, default=list, nullable=False)
    
    views_count = Column(Integer, default=0, nullable=False)
    likes_count = Column(Integer, default=0, nullable=False)
    dislikes_count = Column(Integer, default=0, nullable=False)
    
    is_published = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)


class BlogComment(Base):
    """
    BlogComment Model: Represents a comment on a blog post, supporting threaded replies and moderation.
    """
    __tablename__ = "blog_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = Column(UUID(as_uuid=True), ForeignKey("blog_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Optional parent comment for threaded replies
    parent_id = Column(UUID(as_uuid=True), ForeignKey("blog_comments.id", ondelete="CASCADE"), nullable=True)
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    guest_name = Column(String(255), nullable=True)
    
    content = Column(Text, nullable=False)
    status = Column(String(50), default="pending", nullable=False) # pending, approved, rejected
    
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)
