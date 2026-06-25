from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, json_schema_extra={"example": "St. Peters Welfare"})
    description: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Community fund for emergencies"})

class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, json_schema_extra={"example": "St. Peters Welfare Updated"})
    description: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Updated community fund"})
    currency: Optional[str] = Field(None, min_length=3, max_length=3, json_schema_extra={"example": "USD"})

class GroupOut(BaseModel):
    id: UUID = Field(..., json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"})
    name: str = Field(..., json_schema_extra={"example": "St. Peters Welfare"})
    description: Optional[str] = Field(None, json_schema_extra={"example": "Community fund for emergencies"})
    currency: str = Field(..., json_schema_extra={"example": "KES"})
    status: str = Field(..., json_schema_extra={"example": "active"})
    is_active: bool = Field(..., json_schema_extra={"example": True})
    created_at: datetime

    class Config:
        from_attributes = True
