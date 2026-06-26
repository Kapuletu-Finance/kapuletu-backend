from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID
from enum import Enum

class CurrencyEnum(str, Enum):
    KES = "KES"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"

class GroupStatusEnum(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, json_schema_extra={"example": "St. Peters Welfare"})
    description: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Community fund for emergencies"})
    # Currency defaults to KES on creation but can be specified
    currency: CurrencyEnum = Field(default=CurrencyEnum.KES, json_schema_extra={"example": "KES"})

class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100, json_schema_extra={"example": "St. Peters Welfare Updated"})
    description: Optional[str] = Field(None, max_length=500, json_schema_extra={"example": "Updated community fund"})
    # Currency is intentionally removed from GroupUpdate to enforce immutability

class GroupOut(BaseModel):
    # Map the DB's group_id to the API's id field to fix the 500 serialization error
    id: UUID = Field(validation_alias="group_id", json_schema_extra={"example": "123e4567-e89b-12d3-a456-426614174000"})
    name: str = Field(validation_alias="group_name", json_schema_extra={"example": "St. Peters Welfare"})
    description: Optional[str] = Field(None, json_schema_extra={"example": "Community fund for emergencies"})
    currency: CurrencyEnum = Field(..., json_schema_extra={"example": "KES"})
    status: GroupStatusEnum = Field(..., json_schema_extra={"example": "active"})
    is_active: bool = Field(..., json_schema_extra={"example": True})
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
