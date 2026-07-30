import base64
import io
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, NamedStyle
except ImportError:
    pass

def generate_excel_report(title: str, total_raised: float, target_amount: float, entries: list, settings: dict = None, tz: str = None) -> str:
    """
    Generates an Enterprise-Grade Excel file using openpyxl and returns it as a Base64 string.
    """
    settings = settings or {}
    
    # Process timezone
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    tz = tz or "Africa/Nairobi"
    try:
        from zoneinfo import ZoneInfo
        now_local = now_utc.astimezone(ZoneInfo(tz))
        time_str = now_local.strftime('%d %B %Y at %I:%M %p') + f" ({tz})"
    except Exception:
        time_str = now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')

    wb = openpyxl.Workbook()
    
    # Define currency style
    currency_style = NamedStyle(name="currency")
    currency_style.number_format = '#,##0.00'
    
    # ---------------------------------------------------------
    # SHEET: Campaign Report (Summary + Transactions)
    # ---------------------------------------------------------
    ws = wb.active
    ws.title = "Contributions Report"
    
    # Letterhead
    ws.append([title, "OFFICIAL CAMPAIGN REPORT"])
    ws.cell(row=1, column=1).font = Font(bold=True, color="1A5D1A", size=16)
    ws.cell(row=1, column=2).font = Font(bold=True, size=12, color="555555")
    ws.append([f"Generated on {time_str}"])
    ws.append([])
    
    # Summary Data
    progress = min((float(total_raised) / float(target_amount) * 100), 100.0) if target_amount and float(target_amount) > 0 else 0.0
    
    summary_data = [
        ["Campaign Title", title],
        ["Total Raised (KES)", float(total_raised)],
        ["Target Amount (KES)", float(target_amount)],
        ["Progress (%)", progress]
    ]
    
    for row_idx, row_data in enumerate(summary_data, start=5):
        ws.append(row_data)
        ws.cell(row=row_idx, column=1).font = Font(bold=True)
        # Format Currency
        if "KES" in row_data[0]:
            ws.cell(row=row_idx, column=2).style = currency_style
        # Format Percentage
        if "(%)" in row_data[0]:
            ws.cell(row=row_idx, column=2).number_format = '0.00'
            
    ws.append([])
    ws.append([])
    
    # Transactions Table Header
    headers = ["#", "Transaction Date", "Contributor Name", "Phone Number", "Amount (KES)", "Payment Method"]
    ws.append(headers)
    
    header_row = ws.max_row
    green_fill = PatternFill(start_color="1A5D1A", end_color="1A5D1A", fill_type="solid")
    for cell in ws[header_row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = green_fill
        cell.alignment = Alignment(horizontal="center")
        
    # Transactions Data
    from zoneinfo import ZoneInfo
    for idx, txn in enumerate(entries, 1):
        name = txn.sender_name or (f"Member {txn.sender_phone[-4:]}" if txn.sender_phone else "Anonymous")
        
        # Shift transaction time to target timezone
        txn_time = txn.created_at
        if hasattr(txn_time, 'replace'):
            try:
                txn_time = txn_time.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz))
            except Exception:
                pass
                
        ws.append([
            idx,
            txn_time.strftime("%Y-%m-%d %H:%M"),
            name[:50],
            txn.sender_phone or "-",
            float(txn.amount),
            txn.payment_method or "-"
        ])
        
        # Apply currency format
        ws.cell(row=ws.max_row, column=5).style = currency_style
        
    # Auto-width
    column_widths = {'A': 20, 'B': 25, 'C': 35, 'D': 15, 'E': 15, 'F': 15}
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width
        
    # ---------------------------------------------------------
    # Finalize
    # ---------------------------------------------------------
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    
    return base64.b64encode(stream.getvalue()).decode('utf-8')
