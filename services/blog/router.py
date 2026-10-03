from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_admin_user
from models.users import User
from repositories.blog_repo import BlogRepository
from services.blog.schemas import BlogPostCreate, BlogPostResponse, BlogPostUpdate

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


@router.get("/admin", response_model=List[BlogPostResponse])
def get_all_blogs_admin(
    db: Session = Depends(get_db),
    admin: dict = Depends(get_admin_user)
):
    """Get all blogs including drafts (Admin only)."""
    repo = BlogRepository(db)
    return repo.get_all(include_drafts=True)


@router.post("/admin", response_model=BlogPostResponse, status_code=status.HTTP_201_CREATED)
def create_blog_admin(
    data: BlogPostCreate,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_admin_user)
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
    admin: dict = Depends(get_admin_user)
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
    admin: dict = Depends(get_admin_user)
):
    """Delete a blog post (Admin only)."""
    repo = BlogRepository(db)
    post = repo.get_by_id(post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blog post not found")
        
    repo.delete(post)
    return None
