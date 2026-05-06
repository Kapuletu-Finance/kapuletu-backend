def test_approve_transaction():
    """
    Unit Test: Verifies the state transition logic when a 
    transaction is approved by a treasurer.
    """
    # Note: In a real test, this would use a mock DB session.
    from services.approval.service import approve_transaction
    result = approve_transaction("tx123")
    assert result["status"] == "approved"
