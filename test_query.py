import asyncio
from common.database import SessionLocal
from services.workspace.router import get_workspace_overview
from services.groups.router import list_groups

async def main():
    db = SessionLocal()
    current_user = {"sub": "6c721152-e3a0-458e-a1e9-35afd6d50bfe"}
    try:
        res = await get_workspace_overview(db=db, current_user=current_user)
        print("Overview success!", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

    try:
        res2 = await list_groups(request=None, skip=0, limit=5, search=None, group_status=None, db=db, current_user=current_user)
        print("Groups success!", res2)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
