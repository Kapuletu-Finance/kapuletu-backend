from pydantic import BaseModel

class CampaignSchema(BaseModel):
    name: str
    goal: float
    description: str = ""
