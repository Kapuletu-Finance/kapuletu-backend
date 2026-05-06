class TransactionIn(BaseModel):
    sender_name: str
    amount: float
    transaction_code: str
    phone: str