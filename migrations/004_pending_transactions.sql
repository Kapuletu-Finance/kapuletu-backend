CREATE TABLE pending_transactions (
    pending_id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES users(user_id),
    group_id UUID REFERENCES groups(group_id),
    campaign_id UUID,
    raw_message TEXT NOT NULL,
    sender_name VARCHAR(255),
    amount DECIMAL(12, 2),
    currency VARCHAR(10) DEFAULT 'KES',
    transaction_code VARCHAR(100) UNIQUE,
    sender_phone VARCHAR(20),
    purpose VARCHAR(255),
    confidence_score FLOAT DEFAULT 0.0,
    workflow_status VARCHAR(20) DEFAULT 'pending',
    is_processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);