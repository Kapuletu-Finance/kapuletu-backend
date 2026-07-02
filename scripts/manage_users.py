import argparse
import sys
import os

# Add the root directory to the python path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.database import SessionLocal
from models.users import User
from common.enums import UserRole

def get_user(db, identifier: str):
    """Fetch user by email or phone number"""
    user = db.query(User).filter((User.email == identifier) | (User.phone_number == identifier)).first()
    return user

def delete_user(identifier: str):
    db = SessionLocal()
    try:
        user = get_user(db, identifier)
        if not user:
            print(f"Error: User with identifier '{identifier}' not found.")
            return

        db.delete(user)
        db.commit()
        print(f"Success: User '{identifier}' has been deleted from the database.")
    except Exception as e:
        db.rollback()
        print(f"Failed to delete user: {e}")
    finally:
        db.close()

def elevate_user(identifier: str, role: str):
    db = SessionLocal()
    try:
        # Validate role
        valid_roles = [r.value for r in UserRole]
        if role not in valid_roles:
            print(f"Error: Invalid role '{role}'. Valid roles are: {valid_roles}")
            return

        user = get_user(db, identifier)
        if not user:
            print(f"Error: User with identifier '{identifier}' not found.")
            return

        user.role = role
        db.commit()
        print(f"Success: User '{identifier}' has been elevated to '{role}'.")
    except Exception as e:
        db.rollback()
        print(f"Failed to elevate user: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Users in the Database")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform", required=True)

    # Delete parser
    parser_delete = subparsers.add_parser("delete", help="Delete a user")
    parser_delete.add_argument("identifier", help="User's email or phone number")

    # Elevate parser
    parser_elevate = subparsers.add_parser("elevate", help="Change a user's role")
    parser_elevate.add_argument("identifier", help="User's email or phone number")
    parser_elevate.add_argument("--role", choices=[r.value for r in UserRole], required=True, help="Role to assign (e.g., admin, super_admin)")

    args = parser.parse_args()

    if args.action == "delete":
        delete_user(args.identifier)
    elif args.action == "elevate":
        elevate_user(args.identifier, args.role)
