CREATE TABLE review_actions (
    action_id UUID PRIMARY KEY,
    pending_id UUID REFERENCES pending_transactions(pending_id),
    action_type VARCHAR(20),
    action_by UUID REFERENCES users(user_id),
    internal_note TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);