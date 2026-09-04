import datetime
from sqlalchemy.orm import sessionmaker
from common.database import engine
from models.users import User
from services.auth.auth_service import get_password_hash

Session = sessionmaker(bind=engine)
session = Session()

email = "danielkarume.work@gmail.com"
phone_number = "+254700111222"
password = "Password123!"

user = session.query(User).filter_by(email=email).first()
if not user:
    new_user = User(
        first_name="Daniel",
        last_name="Karume",
        email=email,
        phone_number=phone_number,
        hashed_password=get_password_hash(password),
        role="treasurer",
        is_active=True,
        email_verified=True,
        phone_number_verified=True,
        two_factor_enabled=False,
        allow_ai_training=True,
        created_at=datetime.datetime.now(datetime.UTC)
    )
    session.add(new_user)
    session.commit()
    print(f"User added: {email} / {password}")
else:
    print(f"User already exists: {email}")
