
import sys, os, json, uuid
sys.path.append(os.getcwd())
from common.database import SessionLocal
from models.user import User
from models.group import Group
from models.campaign import Campaign
from common.auth import create_access_token
from services.ingestion.manual_handler import handler

db = SessionLocal()
test_user_id = uuid.uuid4()
test_user = User(user_id=test_user_id, phone_number='+254700000001', email='test_user@example.com', password_hash='fake', role='treasurer', phone_number_verified=True)
db.add(test_user)
other_user_id = uuid.uuid4()
other_user = User(user_id=other_user_id, phone_number='+254700000002', email='other@example.com', password_hash='fake', role='treasurer', phone_number_verified=True)
db.add(other_user)
db.commit()

test_group = Group(owner_id=test_user_id, group_name='Test Group')
db.add(test_group)
db.commit(); db.refresh(test_group)
test_camp = Campaign(group_id=test_group.group_id, title='Test Campaign', target_amount=1000)
db.add(test_camp)
db.commit(); db.refresh(test_camp)
other_group = Group(owner_id=other_user_id, group_name='Other Group')
db.add(other_group)
db.commit(); db.refresh(other_group)

token = create_access_token(data={'sub': str(test_user_id), 'role': 'treasurer'})
def mock_event(b): return {'headers': {'Authorization': f'Bearer {token}'}, 'body': json.dumps(b), 'user_id': str(test_user_id)}

print('\nTEST A: Missing group_id')
print(handler(mock_event({'amount': 500, 'sender_name': 'John'}), None))

print('\nTEST B: Empty group_id')
print(handler(mock_event({'amount': 500, 'sender_name': 'John', 'group_id': '', 'campaign_id': ''}), None))

print('\nTEST C: IDOR Attack (Using other group_id)')
print(handler(mock_event({'amount': 500, 'sender_name': 'John', 'group_id': str(other_group.group_id), 'campaign_id': str(test_camp.campaign_id)}), None))

print('\nTEST D: Valid Submission')
print(handler(mock_event({'amount': 500, 'sender_name': 'John', 'group_id': str(test_group.group_id), 'campaign_id': str(test_camp.campaign_id)}), None))

db.delete(test_camp); db.delete(test_group); db.delete(other_group); db.delete(test_user); db.delete(other_user); db.commit()

