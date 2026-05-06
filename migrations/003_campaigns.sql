CREATE TABLE campaigns (
    campaign_id UUID PRIMARY KEY,
    group_id UUID REFERENCES groups(group_id),
    title VARCHAR(255),
    target_amount DECIMAL(15,2),
    start_date DATE,
    end_date DATE,
    status VARCHAR(20) CHECK (status IN ('active','completed','archived')),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);