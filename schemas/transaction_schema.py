from pydantic import BaseModel


class TransactionIn(BaseModel):
    sender_name: str
    amount: float
    provider: str