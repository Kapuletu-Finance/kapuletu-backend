import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("Testing Blog Features End-to-End...")
    
    # We need an admin token to create a blog
    # For testing, we can just call the router functions directly, or we can use the local server if auth is mocked or we can just test public endpoints if a blog exists.
    # Let's see if any blogs exist first.
    r = requests.get(f"{BASE_URL}/blogs/public")
    if r.status_code != 200:
        print("Failed to fetch public blogs:", r.text)
        return
        
    blogs = r.json()
    if not blogs:
        print("No public blogs exist. Please create one manually in the UI to run the interaction tests.")
        return
        
    blog = blogs[0]
    post_id = blog["id"]
    slug = blog["slug"]
    
    print(f"Using blog: {blog['title']} ({post_id})")
    
    # 1. Test View
    r = requests.post(f"{BASE_URL}/blogs/public/{post_id}/interact?action=view")
    if r.status_code == 200:
        print("✅ View recorded successfully. New views:", r.json()["views_count"])
    else:
        print("❌ Failed to record view:", r.text)

    # 2. Test Like
    r = requests.post(f"{BASE_URL}/blogs/public/{post_id}/interact?action=like")
    if r.status_code == 200:
        print("✅ Like recorded successfully. New likes:", r.json()["likes_count"])
    else:
        print("❌ Failed to record like:", r.text)

    # 3. Test Comment
    comment_data = {
        "post_id": post_id,
        "content": "This is a test comment!",
        "guest_name": "Test Script"
    }
    r = requests.post(f"{BASE_URL}/blogs/public/{post_id}/comments", json=comment_data)
    if r.status_code == 201:
        print("✅ Comment submitted successfully. Status:", r.json()["status"])
    else:
        print("❌ Failed to submit comment:", r.text)
        
if __name__ == "__main__":
    run_tests()
