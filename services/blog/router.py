from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_optional_user, require_role, require_permissions
from common.enums import UserRole
from repositories.blog_repo import BlogRepository
from services.blog.schemas import (
    BlogPostCreate, BlogPostResponse, BlogPostUpdate,
    BlogCommentCreate, BlogCommentResponse
)

router = APIRouter(prefix="/blogs", tags=["Blogs"])


@router.get("/public", response_model=List[BlogPostResponse])
def get_public_blogs(db: Session = Depends(get_db)):
    """Get all published blogs."""
    repo = BlogRepository(db)
    return repo.get_all(include_drafts=False)


@router.get("/public/{slug}", response_model=BlogPostResponse)
def get_public_blog_by_slug(slug: str, db: Session = Depends(get_db)):
    """Get a specific published blog by slug."""
    repo = BlogRepository(db)
    post = repo.get_by_slug(slug, include_drafts=False)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
    return post


@router.post("/public/{post_id}/interact", response_model=BlogPostResponse)
def interact_with_blog(
    post_id: UUID,
    action: str, # "view", "like", "dislike"
    db: Session = Depends(get_db)
):
    """Increment views, likes, or dislikes for a blog post."""
    repo = BlogRepository(db)
    post = repo.get_by_id(post_id)
    if not post or not post.is_published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
        
    if action not in ["view", "like", "dislike"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action")
        
    return repo.increment_metric(post, action)


@router.get("/public/{post_id}/comments", response_model=List[BlogCommentResponse])
def get_blog_comments(
    post_id: UUID,
    db: Session = Depends(get_db)
):
    """Get all approved comments for a blog post."""
    repo = BlogRepository(db)
    post = repo.get_by_id(post_id)
    if not post or not post.is_published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
        
    return repo.get_comments_by_post(post_id, status="approved")


@router.post("/public/{post_id}/comments", response_model=BlogCommentResponse, status_code=status.HTTP_201_CREATED)
def create_blog_comment(
    post_id: UUID,
    data: BlogCommentCreate,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(get_optional_user)
):
    """Submit a new comment (will be set to pending)."""
    repo = BlogRepository(db)
    post = repo.get_by_id(post_id)
    if not post or not post.is_published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
        
    # Validation: Either user is logged in, or they provide a guest_name
    if not user and not data.guest_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Guest name is required for anonymous comments")
        
    # Check parent_id exists if provided
    if data.parent_id:
        parent = repo.get_comment_by_id(data.parent_id)
        if not parent or parent.post_id != post_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parent comment")
            
    user_id = user.get("sub") if user else None
    return repo.create_comment(data, user_id=user_id)


# ==========================================
# ADMIN ENDPOINTS
# ==========================================

@router.get("/admin", response_model=List[BlogPostResponse])
def get_all_blogs_admin(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_permissions(["manage_blogs"]))
):
    """Get all blogs including drafts (Admin only)."""
    repo = BlogRepository(db)
    return repo.get_all(include_drafts=True)


@router.post("/admin", response_model=BlogPostResponse, status_code=status.HTTP_201_CREATED)
def create_blog_admin(
    data: BlogPostCreate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_permissions(["manage_blogs"]))
):
    """Create a new blog post (Admin only)."""
    repo = BlogRepository(db)
    
    # Check if slug exists
    if repo.get_by_slug(data.slug, include_drafts=True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")
        
    return repo.create(data, author_id=admin.get("sub"))


@router.put("/admin/{post_id}", response_model=BlogPostResponse)
def update_blog_admin(
    post_id: UUID,
    data: BlogPostUpdate,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_permissions(["manage_blogs"]))
):
    """Update a blog post (Admin only)."""
    repo = BlogRepository(db)
    post = repo.get_by_id(post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
        
    # Check if slug exists and belongs to a different post
    if data.slug and data.slug != post.slug:
        if repo.get_by_slug(data.slug, include_drafts=True):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug already exists")
            
    return repo.update(post, data)


@router.delete("/admin/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_blog_admin(
    post_id: UUID,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_permissions(["manage_blogs"]))
):
    """Delete a blog post (Admin only)."""
    repo = BlogRepository(db)
    post = repo.get_by_id(post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
        
    repo.delete(post)
    return None


@router.get("/admin/comments", response_model=List[BlogCommentResponse])
def get_all_comments_admin(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_permissions(["manage_blogs"]))
):
    """Get all comments, optionally filtered by status (Admin only)."""
    repo = BlogRepository(db)
    return repo.get_all_comments(status=status_filter)


@router.patch("/admin/comments/{comment_id}/status", response_model=BlogCommentResponse)
def update_comment_status_admin(
    comment_id: UUID,
    status: str, # "pending", "approved", "rejected"
    db: Session = Depends(get_db),
    admin: dict = Depends(require_permissions(["manage_blogs"]))
):
    """Approve or reject a comment (Admin only)."""
    if status not in ["pending", "approved", "rejected"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
        
    repo = BlogRepository(db)
    comment = repo.get_comment_by_id(comment_id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
        
    return repo.update_comment_status(comment, status)
