from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date

class EmployeeReportCreate(BaseModel):
    work_summary: str

class EmployeeReportResponse(BaseModel):
    id: str
    user_id: str
    report_date: date
    clock_in_time: Optional[datetime]
    clock_out_time: Optional[datetime]
    work_summary: Optional[str]
    status: str
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

class MeetingCreate(BaseModel):
    title: str
    description: Optional[str]
    meeting_type: str
    location_or_url: Optional[str]
    start_time: datetime
    end_time: datetime
    attendee_ids: list[str]

class MeetingResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    meeting_type: str
    location_or_url: Optional[str]
    start_time: datetime
    end_time: datetime
    organizer_id: str
    created_at: datetime
