from pydantic import BaseModel

class MemberSchema(BaseModel):
    name: str
    phone: str
    group_id: str = None
