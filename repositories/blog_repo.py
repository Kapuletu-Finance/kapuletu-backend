from typing import List, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.blog import BlogPost
from services.blog.schemas import BlogPostCreate, BlogPostUpdate


class BlogRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, include_drafts: bool = False) -> List[BlogPost]:
        query = self.db.query(BlogPost)
        if not include_drafts:
            query = query.filter(BlogPost.is_published == True)
        return query.order_by(desc(BlogPost.created_at)).all()

    def get_by_id(self, post_id: UUID) -> Optional[BlogPost]:
        return self.db.query(BlogPost).filter(BlogPost.id == post_id).first()

    def get_by_slug(self, slug: str, include_drafts: bool = False) -> Optional[BlogPost]:
        query = self.db.query(BlogPost).filter(BlogPost.slug == slug)
        if not include_drafts:
            query = query.filter(BlogPost.is_published == True)
        return query.first()

    def create(self, data: BlogPostCreate, author_id: Optional[UUID] = None) -> BlogPost:
        post = BlogPost(
            **data.dict(),
            author_id=author_id,
        )
        if post.is_published:
            post.published_at = datetime.utcnow()
            
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)
        return post

    def update(self, post: BlogPost, data: BlogPostUpdate) -> BlogPost:
        update_data = data.dict(exclude_unset=True)
        
        # Handle publish date if status changed
        if "is_published" in update_data:
            if update_data["is_published"] and not post.is_published:
                post.published_at = datetime.utcnow()
            elif not update_data["is_published"] and post.is_published:
                post.published_at = None

        for key, value in update_data.items():
            setattr(post, key, value)
            
        self.db.commit()
        self.db.refresh(post)
        return post

    def delete(self, post: BlogPost) -> None:
        self.db.delete(post)
        self.db.commit()
