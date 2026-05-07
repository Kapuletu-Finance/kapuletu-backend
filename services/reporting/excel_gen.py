import base64
import io

import pandas as pd


def generate_excel_report(transactions_data: list):
    """
    Converts a list of transaction records into an Excel file.
    Returns a Base64 encoded string suitable for API responses.
    """
    if not transactions_data:
        return None

    # Create a DataFrame
    df = pd.DataFrame(transactions_data)
    
    # Prettify column names
    df.columns = [col.replace('_', ' ').title() for col in df.columns]

    # Write to an in-memory buffer
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transactions')
    
    # Get the raw bytes
    excel_data = output.getvalue()
    
    # Encode to Base64
    return base64.b64encode(excel_data).decode('utf-8')
