class CampaignCreate(BaseModel):
    title: str
    target_amount: float
    group_id: str