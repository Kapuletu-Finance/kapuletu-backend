from pydantic import BaseModel


class UserLogin(BaseModel):
    phone_number: str
    password: str