import datetime
import uuid
from sqlalchemy.orm import sessionmaker
from common.database import engine
from models.users import User
from services.auth.auth_service import get_password_hash
from common.enums import UserRole

def seed_local_users():
    Session = sessionmaker(bind=engine)
    session = Session()

    admin_email = "admin@kapuletu.local"
    treasurer_email = "treasurer@kapuletu.local"
    password = "Password123!"

    # Create Admin User
    admin = session.query(User).filter_by(email=admin_email).first()
    if not admin:
        new_admin = User(
            user_id=uuid.uuid4(),
            first_name="Admin",
            last_name="User",
            email=admin_email,
            phone_number="+254700000001",
            hashed_password=get_password_hash(password),
            role=UserRole.ADMIN.value,
            is_active=True,
            email_verified=True,
            phone_number_verified=True,
            created_at=datetime.datetime.utcnow()
        )
        session.add(new_admin)
        print(f"Admin user created: {admin_email} / {password}")
    else:
        print(f"Admin user already exists: {admin_email}")

    # Create Treasurer User
    treasurer = session.query(User).filter_by(email=treasurer_email).first()
    if not treasurer:
        new_treasurer = User(
            user_id=uuid.uuid4(),
            first_name="Treasurer",
            last_name="User",
            email=treasurer_email,
            phone_number="+254700000002",
            hashed_password=get_password_hash(password),
            role=UserRole.TREASURER.value,
            is_active=True,
            email_verified=True,
            phone_number_verified=True,
            created_at=datetime.datetime.utcnow()
        )
        session.add(new_treasurer)
        print(f"Treasurer user created: {treasurer_email} / {password}")
    else:
        print(f"Treasurer user already exists: {treasurer_email}")

    session.commit()
    print("Local seeding complete!")

if __name__ == "__main__":
    seed_local_users()
