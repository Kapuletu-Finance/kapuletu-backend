from pydantic import BaseModel


class Allocation(BaseModel):
    member_name: str
    amount: float
    mode: str