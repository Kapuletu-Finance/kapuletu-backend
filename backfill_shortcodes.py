import sys
import os
from dotenv import load_dotenv

# Add the project directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from common.database import SessionLocal
from models.campaign import Campaign
import uuid

def generate_short_code():
    return uuid.uuid4().hex[:8]

def backfill():
    db = SessionLocal()
    try:
        campaigns = db.query(Campaign).filter(Campaign.short_code == None).all()
        print(f"Found {len(campaigns)} campaigns missing short codes.")
        for c in campaigns:
            c.short_code = generate_short_code()
            print(f"Assigning shortcode {c.short_code} to campaign {c.title}")
        db.commit()
        print("Backfill complete.")
    finally:
        db.close()

if __name__ == '__main__':
    backfill()
