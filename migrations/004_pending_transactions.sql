CREATE TABLE pending_transactions (
    pending_id UUID PRIMARY KEY,
    owner_id UUID REFERENCES users(user_id),
    group_id UUID REFERENCES groups(group_id),
    campaign_id UUID NULL,

    raw_message TEXT,
    message_attachments JSONB,

    source_channel VARCHAR(20),

    source_reference_id VARCHAR(100),
    idempotency_key VARCHAR(100) UNIQUE,

    extracted_code VARCHAR(50),
    extracted_sender_name TEXT,
    extracted_amount DECIMAL(15,2),
    extracted_phone VARCHAR(20),
    extracted_date TIMESTAMP,

    parsing_status VARCHAR(20),
    parser_warning_flag TEXT,
    confidence_score DECIMAL(5,2),

    workflow_status VARCHAR(30),
    assigned_treasurer_id UUID,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);