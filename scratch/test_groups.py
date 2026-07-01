import requests
import time

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("--- Testing Groups CRUD ---")
    
    # 1. Login to get token
    print("1. Logging in...")
    resp = requests.post(
        f"{BASE_URL}/auth/token", 
        data={"username": "+254115749711", "password": "Joseph@2026!", "grant_type": "password"}
    )
    if resp.status_code != 200:
        print(f"Login Failed: {resp.text}")
        return
        
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("Login successful.")

    # 2. Create Group
    print("\n2. Creating Group...")
    payload = {
        "name": f"Test Group {int(time.time())}",
        "description": "A group created via automated test",
        "currency": "KES"
    }
    resp = requests.post(f"{BASE_URL}/groups", json=payload, headers=headers)
    if resp.status_code != 201:
        print(f"Create Failed: {resp.text}")
        return
    group = resp.json()
    group_id = group["id"]
    print(f"Group created successfully: {group_id}")

    # 3. List Groups (Test Pagination)
    print("\n3. Listing Groups (Pagination)...")
    resp = requests.get(f"{BASE_URL}/groups?skip=0&limit=5", headers=headers)
    if resp.status_code != 200:
        print(f"List Failed: {resp.text}")
        return
    groups = resp.json()
    print(f"Found {len(groups)} active groups.")
    
    # 4. Get Single Group
    print("\n4. Getting Single Group...")
    resp = requests.get(f"{BASE_URL}/groups/{group_id}", headers=headers)
    if resp.status_code != 200:
        print(f"Get Failed: {resp.text}")
        return
    print(f"Retrieved group: {resp.json()['name']}")
    
    # 5. Update Group
    print("\n5. Updating Group...")
    update_payload = {"description": "Updated via automated test"}
    resp = requests.patch(f"{BASE_URL}/groups/{group_id}", json=update_payload, headers=headers)
    if resp.status_code != 200:
        print(f"Update Failed: {resp.text}")
        return
    print(f"Updated group description: {resp.json()['description']}")
    
    # 6. Archive Group
    print("\n6. Archiving Group...")
    resp = requests.delete(f"{BASE_URL}/groups/{group_id}", headers=headers)
    if resp.status_code != 200:
        print(f"Archive Failed: {resp.text}")
        return
    print(f"Group archived successfully. is_active={resp.json()['is_active']}")
    
    print("\n--- All Groups tests passed successfully! ---")

if __name__ == "__main__":
    run_tests()
