def test_parse_message():
    """
    Unit Test: Verifies that the parser engine can extract amounts 
    from a simple currency string.
    """
    from services.ingestion.parser_engine import parse_message
    result = parse_message("KES 500 from 254700000000")
    # Assert that the cleaned amount is correctly identified
    assert result["amount"] == "500"
