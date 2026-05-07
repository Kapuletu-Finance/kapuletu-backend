from pydantic import BaseModel


class CampaignCreate(BaseModel):
    title: str
    target_amount: float