CREATE TABLE transactions (
    transaction_id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES users(user_id),
    group_id UUID NOT NULL REFERENCES groups(group_id),
    campaign_id UUID REFERENCES campaigns(campaign_id),
    transaction_code VARCHAR(100) UNIQUE NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    sender_phone VARCHAR(20),
    status VARCHAR(20) DEFAULT 'approved',
    created_at TIMESTAMP DEFAULT NOW()
);