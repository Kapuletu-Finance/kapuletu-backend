from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class BlogPostBase(BaseModel):
    title: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    excerpt: Optional[str] = Field(None, max_length=500)
    content: str
    cover_image_url: Optional[str] = Field(None, max_length=1024)
    category: Optional[str] = Field(None, max_length=100)
    author_name: Optional[str] = Field(None, max_length=255)
    author_role: Optional[str] = Field(None, max_length=255)
    is_published: bool = False


class BlogPostCreate(BlogPostBase):
    pass


class BlogPostUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    excerpt: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = None
    cover_image_url: Optional[str] = Field(None, max_length=1024)
    category: Optional[str] = Field(None, max_length=100)
    author_name: Optional[str] = Field(None, max_length=255)
    author_role: Optional[str] = Field(None, max_length=255)
    is_published: Optional[bool] = None


class BlogPostResponse(BlogPostBase):
    id: UUID
    author_id: Optional[UUID] = None
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
