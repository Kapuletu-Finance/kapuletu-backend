from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
import os
import uuid
from typing import Dict, Any

from common.auth_dependencies import get_current_user

router = APIRouter(prefix="/upload", tags=["Uploads"])

@router.post("/image", summary="Upload a generic image (e.g. for blogs)")
async def upload_image(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Uploads an image file to local storage and returns its accessible URL.
    This can be used for blog cover images, in-content images, etc.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
        
    os.makedirs("uploads", exist_ok=True)
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    unique_filename = f"img_{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join("uploads", unique_filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    image_url = f"/uploads/{unique_filename}"
    
    return {"url": image_url, "filename": file.filename}
