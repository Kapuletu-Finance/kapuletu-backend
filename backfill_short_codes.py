import asyncio
import secrets
from sqlalchemy import select
from common.database import SessionLocal
from models.campaign import Campaign

async def main():
    print("Backfilling short codes for campaigns...")
    async with SessionLocal() as db:
        result = await db.execute(select(Campaign).where(Campaign.short_code == None))
        campaigns = result.scalars().all()
        for campaign in campaigns:
            short_code = secrets.token_hex(3)
            # Ensure uniqueness
            while True:
                exists = await db.execute(select(Campaign).where(Campaign.short_code == short_code))
                if not exists.scalars().first():
                    break
                short_code = secrets.token_hex(3)
            
            campaign.short_code = short_code
            print(f"Assigned short code {short_code} to campaign {campaign.title}")
            
        await db.commit()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
