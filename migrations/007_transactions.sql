CREATE TABLE transactions (
    transaction_id UUID PRIMARY KEY,
    pending_id UUID,
    owner_id UUID REFERENCES users(user_id),
    group_id UUID REFERENCES groups(group_id),
    campaign_id UUID REFERENCES campaigns(campaign_id),

    transaction_code VARCHAR(100),
    total_amount DECIMAL(15,2),

    status VARCHAR(20),

    ledger_id VARCHAR(100),

    created_at TIMESTAMP DEFAULT NOW()
);