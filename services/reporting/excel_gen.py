import base64
import io
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, NamedStyle
except ImportError:
    pass

def generate_excel_report(title: str, total_raised: float, target_amount: float, entries: list, settings: dict = None, tz: str = None, campaign=None) -> str:
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
    
    from services.reporting.shared import process_template
    
    raw_title = settings.get("report_title", "")
    if campaign:
        display_title = process_template(raw_title, campaign, total_raised)
    else:
        display_title = title
    
    if display_title:
        # We put the display_title in the first cell, and enable text wrapping
        header_cell = ws.cell(row=1, column=1, value=display_title)
        header_cell.font = Font(bold=True, color="1A5D1A", size=14)
        header_cell.alignment = Alignment(wrap_text=True)
        # We can increase the row height to accommodate multi-line text
        lines_count = display_title.count('\n') + 1
        ws.row_dimensions[1].height = 20 * lines_count
    
    # Add Logo
    import os
    try:
        from openpyxl.drawing.image import Image as OpenPyXLImage
        logo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "logos", "primary logo.png")
        if os.path.exists(logo_path):
            img = OpenPyXLImage(logo_path)
            target_height = 50
            aspect_ratio = img.width / img.height
            img.height = target_height
            img.width = int(target_height * aspect_ratio)
            ws.add_image(img, 'D1')
    except Exception:
        pass
        
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
            txn_time.strftime("%Y-%m-%d %I:%M %p"),
            name[:50],
            txn.sender_phone or "-",
            float(txn.amount),
            txn.payment_method or "-"
        ])
        
        # Apply currency format
        ws.cell(row=ws.max_row, column=5).style = currency_style
        
    try:
        blank_slots = int(settings.get("blank_slots", 0))
    except (ValueError, TypeError):
        blank_slots = 0
        
    current_idx = len(entries) + 1
    for _ in range(blank_slots):
        ws.append([current_idx, "", "", "", "", ""])
        current_idx += 1
        
    # Auto-width
    column_widths = {'A': 20, 'B': 25, 'C': 35, 'D': 15, 'E': 15, 'F': 15}
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width
        
    raw_footer = settings.get("report_footer")
    if raw_footer:
        if campaign:
            processed_footer = process_template(raw_footer, campaign, total_raised)
        else:
            processed_footer = raw_footer
            
        if processed_footer:
            ws.append([])
            ws.append([processed_footer])
            footer_cell = ws.cell(row=ws.max_row, column=1)
            footer_cell.font = Font(italic=True, color="555555")
            footer_cell.alignment = Alignment(wrap_text=True)
            lines_count = processed_footer.count('\n') + 1
            ws.row_dimensions[ws.max_row].height = 15 * lines_count
        
    # ---------------------------------------------------------
    # Finalize
    # ---------------------------------------------------------
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    
    return base64.b64encode(stream.getvalue()).decode('utf-8')
