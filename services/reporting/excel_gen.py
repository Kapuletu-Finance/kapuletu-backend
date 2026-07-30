import base64
import io
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, NamedStyle
except ImportError:
    pass

def generate_excel_report(title: str, group_name: str, total_raised: float, target_amount: float, entries: list, settings: dict = None) -> str:
    """
    Generates an Enterprise-Grade Excel file using openpyxl and returns it as a Base64 string.
    """
    settings = settings or {}
    wb = openpyxl.Workbook()
    
    # Define currency style
    currency_style = NamedStyle(name="currency")
    currency_style.number_format = '#,##0.00'
    
    # ---------------------------------------------------------
    # SHEET 1: Summary Sheet
    # ---------------------------------------------------------
    ws_summary = wb.active
    ws_summary.title = "Summary"
    
    # Letterhead
    ws_summary.append([title, "OFFICIAL CAMPAIGN REPORT"])
    ws_summary.cell(row=1, column=1).font = Font(bold=True, color="1A5D1A", size=16)
    ws_summary.cell(row=1, column=2).font = Font(bold=True, size=12, color="555555")
    ws_summary.append([f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"])
    ws_summary.append([])
    
    # Summary Data
    progress = min((float(total_raised) / float(target_amount) * 100), 100.0) if target_amount and float(target_amount) > 0 else 0.0
    
    summary_data = [
        ["Campaign Title", title],
        ["Total Raised (KES)", float(total_raised)],
        ["Target Amount (KES)", float(target_amount)],
        ["Progress (%)", progress]
    ]
    
    for row_idx, row_data in enumerate(summary_data, start=5):
        ws_summary.append(row_data)
        ws_summary.cell(row=row_idx, column=1).font = Font(bold=True)
        # Format Currency
        if "KES" in row_data[0]:
            ws_summary.cell(row=row_idx, column=2).style = currency_style
        # Format Percentage
        if "(%)" in row_data[0]:
            ws_summary.cell(row=row_idx, column=2).number_format = '0.00'
            
    # Auto-width
    ws_summary.column_dimensions['A'].width = 25
    ws_summary.column_dimensions['B'].width = 40
    
    # ---------------------------------------------------------
    # SHEET 2: Transactions
    # ---------------------------------------------------------
    ws_tx = wb.create_sheet(title="Transactions")
    
    headers = ["#", "Transaction Date", "Contributor Name", "Phone Number", "Amount (KES)", "Payment Method"]
    ws_tx.append(headers)
    
    # Style headers
    green_fill = PatternFill(start_color="1A5D1A", end_color="1A5D1A", fill_type="solid")
    for cell in ws_tx[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = green_fill
        cell.alignment = Alignment(horizontal="center")
        
    for idx, txn in enumerate(entries, 1):
        name = txn.sender_name or (f"Member {txn.sender_phone[-4:]}" if txn.sender_phone else "Anonymous")
        ws_tx.append([
            idx,
            txn.created_at.strftime("%Y-%m-%d %H:%M"),
            name[:50],
            txn.sender_phone or "-",
            float(txn.amount),
            txn.payment_method or "-"
        ])
        
        # Apply currency format
        ws_tx.cell(row=idx+1, column=5).style = currency_style
        
    # Auto-width
    column_widths = {'A': 5, 'B': 20, 'C': 35, 'D': 15, 'E': 15, 'F': 15}
    for col, width in column_widths.items():
        ws_tx.column_dimensions[col].width = width
        
    # ---------------------------------------------------------
    # Finalize
    # ---------------------------------------------------------
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    
    return base64.b64encode(stream.getvalue()).decode('utf-8')
