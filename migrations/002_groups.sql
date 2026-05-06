CREATE TABLE groups (
    group_id UUID PRIMARY KEY,
    owner_id UUID REFERENCES users(user_id),
    group_name VARCHAR(255),
    currency VARCHAR(3) DEFAULT 'KES',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);