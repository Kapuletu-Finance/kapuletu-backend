from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

app = FastAPI()
router = APIRouter()

@app.get("/test")
def impl(): return "impl"

@router.get("/test")
def schema(): return "schema"

app.include_router(router)

client = TestClient(app)
print(client.get("/test").json())
