import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Channel = Literal["email", "in_app", "whatsapp"]
Category = Literal["service", "marketing"]
AudienceType = Literal["all_users", "customers", "staff", "subscription", "selected_users"]
SubscriptionState = Literal["paid", "trial", "comp", "lapsed", "free"]


class AudienceIn(BaseModel):
    type: AudienceType
    states: Optional[List[SubscriptionState]] = Field(None, description="For type=subscription")
    user_ids: Optional[List[str]] = Field(None, description="For type=selected_users", max_length=10_000)


class EmailContentIn(BaseModel):
    subject: str = Field(..., max_length=200)
    html: str = Field(..., max_length=200_000)
    preheader: Optional[str] = Field(None, max_length=200, description="Inbox preview text")


class InAppContentIn(BaseModel):
    title: str = Field(..., max_length=120)
    body: str = Field(..., max_length=2000)


class WhatsAppContentIn(BaseModel):
    template: str = Field(..., description="Name of a template approved in Meta Business Manager")
    language: str = Field("en", description="Template language code, e.g. en or en_US")
    params: List[str] = Field(default_factory=list, description="Body variables {{1}}, {{2}}… in order")


class ContentIn(BaseModel):
    email: Optional[EmailContentIn] = None
    in_app: Optional[InAppContentIn] = Field(None, description="Defaults to the email subject and text")
    whatsapp: Optional[WhatsAppContentIn] = None


class BroadcastEstimateIn(BaseModel):
    category: Category = "service"
    audience: AudienceIn
    channels: List[Channel] = Field(..., min_length=1)


class BroadcastCreateIn(BroadcastEstimateIn):
    title: str = Field(..., min_length=3, max_length=255, description="Internal name shown in the history")
    content: ContentIn
    scheduled_for: Optional[datetime.datetime] = Field(None, description="Send later; omit to send now")


class DecisionIn(BaseModel):
    note: Optional[str] = Field(None, max_length=1000)


class SuppressionIn(BaseModel):
    channel: Literal["email", "whatsapp"]
    destination: str = Field(..., max_length=255)
    category: Literal["all", "marketing"] = "all"
    note: Optional[str] = Field(None, max_length=500)


class TemplateSaveIn(BaseModel):
    content: str
    note: Optional[str] = Field(None, max_length=255)


class TemplatePreviewIn(BaseModel):
    content: Optional[str] = Field(None, description="Unsaved editor content; omit to preview the saved template")
    message: Optional[str] = Field(None, max_length=5000)
