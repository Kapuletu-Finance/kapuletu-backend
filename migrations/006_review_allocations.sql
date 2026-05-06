CREATE TABLE review_allocations (
    allocation_id UUID PRIMARY KEY,
    pending_id UUID REFERENCES pending_transactions(pending_id),
    action_id UUID REFERENCES review_actions(action_id),

    member_name VARCHAR(150),
    member_phone VARCHAR(20),

    allocated_amount DECIMAL(15,2),

    allocation_mode VARCHAR(30),

    allocation_sequence INTEGER,

    created_at TIMESTAMP DEFAULT NOW()
);