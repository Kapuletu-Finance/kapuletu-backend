from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from uuid import UUID

class EmployeeClockInCreate(BaseModel):
    work_mode: str # "physical" or "remote"
    latitude: Optional[str] = None
    longitude: Optional[str] = None

class EmployeeReportCreate(BaseModel):
    work_summary: str

class EmployeeReportResponse(BaseModel):
    id: UUID
    user_id: UUID
    report_date: date
    clock_in_time: Optional[datetime]
    clock_out_time: Optional[datetime]
    work_summary: Optional[str]
    status: str
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class MeetingCreate(BaseModel):
    title: str
    description: Optional[str]
    meeting_type: str
    location_or_url: Optional[str]
    start_time: datetime
    end_time: datetime
    attendee_ids: list[UUID]

class MeetingResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    meeting_type: str
    location_or_url: Optional[str]
    start_time: datetime
    end_time: datetime
    organizer_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
