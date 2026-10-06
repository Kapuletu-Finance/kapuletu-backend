from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
import json

class BlogPostBase(BaseModel):
    title: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    excerpt: Optional[str] = Field(None, max_length=500)
    content: str
    cover_image_url: Optional[str] = Field(None, max_length=1024)
    category: Optional[str] = Field(None, max_length=100)
    tags: List[str] = Field(default_factory=list)
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
    tags: Optional[List[str]] = None
    author_name: Optional[str] = Field(None, max_length=255)
    author_role: Optional[str] = Field(None, max_length=255)
    is_published: Optional[bool] = None


class BlogPostResponse(BlogPostBase):
    id: UUID
    author_id: Optional[UUID] = None
    views_count: int = 0
    likes_count: int = 0
    dislikes_count: int = 0
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @field_validator('tags', mode='before')
    def parse_tags(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return []
        return v or []

    class Config:
        orm_mode = True
        from_attributes = True


class BlogCommentBase(BaseModel):
    content: str = Field(..., max_length=2000)
    guest_name: Optional[str] = Field(None, max_length=255)
    parent_id: Optional[UUID] = None


class BlogCommentCreate(BlogCommentBase):
    post_id: UUID


class BlogCommentResponse(BlogCommentBase):
    id: UUID
    post_id: UUID
    user_id: Optional[UUID] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True
