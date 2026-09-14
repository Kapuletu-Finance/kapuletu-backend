import datetime
import random
import uuid
from sqlalchemy.orm import sessionmaker
from common.database import engine
from models.users import User
from models.pending_transaction import PendingTransaction

Session = sessionmaker(bind=engine)
session = Session()

email = "danielkarume.work@gmail.com"
user = session.query(User).filter_by(email=email).first()

if not user:
    print(f"User {email} not found!")
    exit(1)

print(f"Found user {user.user_id}, adding 50 inbox items...")

names = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Heidi", "Ivan", "Judy", "Ken", "Lucy", "Mike", "Nina", "Oscar", "Pam", "Quinn", "Ray", "Sam", "Tina"]
purposes = ["January Dues", "Wedding Contribution", "Funeral Contribution", "General Fund", "Party", "School Fees", "Medical Bill"]

for i in range(50):
    tx_code = f"MPESA{random.randint(10000000, 99999999)}"
    amount = random.randint(5, 50) * 100
    sender = f"{random.choice(names)} {random.choice(names)}"
    pt = PendingTransaction(
        owner_id=user.user_id,
        raw_message=f"{tx_code} Confirmed. Ksh{amount} sent to You from {sender}.",
        sender_name=sender,
        amount=amount,
        currency="KES",
        transaction_code=tx_code,
        sender_phone=f"+2547{random.randint(10000000, 99999999)}",
        purpose=random.choice(purposes),
        original_ai_output={},
        confidence_score=round(random.uniform(0.7, 0.99), 2),
        workflow_status="pending",
        is_processed=False,
        payment_method="M-Pesa",
        source_evidence="SMS",
        created_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=random.randint(1, 10000))
    )
    session.add(pt)

session.commit()
print("Successfully added 50 inbox items.")
