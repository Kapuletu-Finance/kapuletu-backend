CREATE TABLE audit_logs (
    log_id BIGSERIAL PRIMARY KEY,
    actor_id UUID REFERENCES users(user_id),
    action VARCHAR(50),
    entity_type VARCHAR(50),
    entity_id UUID,

    previous_values JSONB,
    new_values JSONB,

    ip_address VARCHAR(45),

    created_at TIMESTAMP DEFAULT NOW()
);