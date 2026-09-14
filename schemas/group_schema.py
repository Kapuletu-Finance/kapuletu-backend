from pydantic import BaseModel


class GroupCreate(BaseModel):
    group_name: str
    currency: str = "KES"