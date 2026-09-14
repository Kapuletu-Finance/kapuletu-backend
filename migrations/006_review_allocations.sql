CREATE TABLE review_allocations (
    allocation_id UUID PRIMARY KEY,
    transaction_id UUID REFERENCES transactions(transaction_id),
    pending_id UUID REFERENCES pending_transactions(pending_id),
    member_name VARCHAR(255),
    allocated_amount DECIMAL(12, 2)
);