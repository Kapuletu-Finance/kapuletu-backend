def create_campaign(data):
    return {"id": "1", "name": data.get("name"), "status": "active"}

def list_campaigns():
    return [{"id": "1", "name": "General Fund"}]
