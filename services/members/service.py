def create_member(data):
    return {"id": "1", "name": data.get("name"), "status": "created"}

def list_members():
    return [{"id": "1", "name": "John Doe"}]
