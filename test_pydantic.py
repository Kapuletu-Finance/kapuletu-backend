from pydantic import BaseModel, Field, ConfigDict
from uuid import uuid4, UUID

class GroupOut(BaseModel):
    id: UUID = Field(validation_alias="group_id")
    name: str = Field(validation_alias="group_name")
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class Group:
    def __init__(self):
        self.group_id = uuid4()
        self.group_name = "Test Group"

try:
    g = Group()
    out = GroupOut.model_validate(g)
    print("Success:", out.model_dump())
except Exception as e:
    import traceback
    traceback.print_exc()
