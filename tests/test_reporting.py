def test_generate_summary():
    """
    Unit Test: Ensures that the summary reporting logic 
    returns the expected financial metrics.
    """
    from services.reporting.daily_summary import generate_summary
    result = generate_summary()
    # Verify that the core aggregation metric is present
    assert "total_collected" in result
