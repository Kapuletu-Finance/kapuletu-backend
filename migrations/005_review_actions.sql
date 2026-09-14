CREATE TABLE review_actions (
    action_id UUID PRIMARY KEY,
    pending_id UUID NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);