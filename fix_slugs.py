import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from common.database import SessionLocal
from models.campaign import Campaign
from models.group import Group
from common.utils import generate_slug
import random

def fix_missing_slugs():
    db: Session = SessionLocal()
    try:
        # Fix Campaigns
        campaigns = db.query(Campaign).filter((Campaign.slug == None) | (Campaign.slug == "")).all()
        camp_count = 0
        for camp in campaigns:
            base_slug = generate_slug(camp.title) if camp.title else ""
            if not base_slug:
                base_slug = f"campaign-{random.randint(1000, 9999)}"
            
            slug = base_slug
            while db.query(Campaign).filter(Campaign.group_id == camp.group_id, Campaign.slug == slug).first():
                slug = f"{base_slug}-{random.randint(1000, 9999)}"
                
            camp.slug = slug
            camp_count += 1
            
        # Fix Groups
        groups = db.query(Group).filter((Group.slug == None) | (Group.slug == "")).all()
        group_count = 0
        for group in groups:
            base_slug = generate_slug(group.group_name) if group.group_name else ""
            if not base_slug:
                base_slug = f"group-{random.randint(1000, 9999)}"
            
            slug = base_slug
            while db.query(Group).filter(Group.owner_id == group.owner_id, Group.slug == slug).first():
                slug = f"{base_slug}-{random.randint(1000, 9999)}"
                
            group.slug = slug
            group_count += 1
            
        db.commit()
        print(f"Successfully updated {camp_count} campaigns and {group_count} groups with missing slugs.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_missing_slugs()
