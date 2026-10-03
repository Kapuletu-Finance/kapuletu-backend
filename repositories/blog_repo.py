from typing import List, Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.blog import BlogPost, BlogComment
from services.blog.schemas import BlogPostCreate, BlogPostUpdate, BlogCommentCreate


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

    def increment_metric(self, post: BlogPost, metric: str) -> BlogPost:
        if metric == "view":
            post.views_count += 1
        elif metric == "like":
            post.likes_count += 1
        elif metric == "dislike":
            post.dislikes_count += 1
            
        self.db.commit()
        self.db.refresh(post)
        return post

    def create_comment(self, data: BlogCommentCreate, user_id: Optional[UUID] = None) -> BlogComment:
        comment = BlogComment(
            **data.dict(),
            user_id=user_id
        )
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def get_comments_by_post(self, post_id: UUID, status: str = "approved") -> List[BlogComment]:
        query = self.db.query(BlogComment).filter(BlogComment.post_id == post_id)
        if status:
            query = query.filter(BlogComment.status == status)
        return query.order_by(BlogComment.created_at).all()

    def get_all_comments(self, status: Optional[str] = None) -> List[BlogComment]:
        query = self.db.query(BlogComment)
        if status:
            query = query.filter(BlogComment.status == status)
        return query.order_by(desc(BlogComment.created_at)).all()

    def get_comment_by_id(self, comment_id: UUID) -> Optional[BlogComment]:
        return self.db.query(BlogComment).filter(BlogComment.id == comment_id).first()

    def update_comment_status(self, comment: BlogComment, status: str) -> BlogComment:
        comment.status = status
        self.db.commit()
        self.db.refresh(comment)
        return comment
