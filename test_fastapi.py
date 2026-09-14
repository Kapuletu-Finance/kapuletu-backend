import asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, ConfigDict
from uuid import uuid4, UUID
from typing import List

app = FastAPI()

class GroupOut(BaseModel):
    id: UUID = Field(validation_alias="group_id")
    name: str = Field(validation_alias="group_name")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class Paginated(BaseModel):
    items: List[GroupOut]

class Group:
    def __init__(self):
        self.group_id = uuid4()
        self.group_name = "Test Group"

@app.get("/test", response_model=Paginated)
def test_endpoint():
    return {"items": [Group()]}

client = TestClient(app)
try:
    response = client.get("/test")
    print(response.status_code, response.json())
except Exception as e:
    import traceback
    traceback.print_exc()
