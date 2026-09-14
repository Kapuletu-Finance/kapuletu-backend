CREATE TABLE campaigns (
    campaign_id UUID PRIMARY KEY,
    group_id UUID NOT NULL REFERENCES groups(group_id),
    title VARCHAR(255) NOT NULL,
    target_amount DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT NOW()
);