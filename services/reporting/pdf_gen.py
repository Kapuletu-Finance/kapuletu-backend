import base64
import os
from fpdf import FPDF
from datetime import datetime

class KapuletuPDF(FPDF):
    def header(self):
        # Arial bold 15
        self.set_font('Arial', 'B', 15)
        # Title
        self.cell(0, 10, 'KAPULETU TREASURY REPORT', 0, 1, 'C')
        self.set_font('Arial', '', 10)
        self.cell(0, 10, f'Generated on {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        # Arial italic 8
        self.set_font('Arial', 'I', 8)
        # Page number
        self.cell(0, 10, 'Page ' + str(self.page_no()) + ' / {nb}', 0, 0, 'C')

def generate_pdf_report(campaign_title: str, total_raised: float, target_amount: float, entries: list) -> str:
    """
    Generates a PDF using FPDF and returns it as a Base64 string.
    Note: Requires `fpdf2` or `fpdf` package.
    """
    pdf = KapuletuPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # Campaign Summary
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f'Campaign: {campaign_title}', 0, 1)
    
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f'Total Raised: KSh. {total_raised:,.2f}', 0, 1)
    if target_amount > 0:
        pdf.cell(0, 10, f'Target Amount: KSh. {target_amount:,.2f}', 0, 1)
        
    pdf.ln(10)
    
    # Table Header
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(10, 10, '#', 1)
    pdf.cell(80, 10, 'Name', 1)
    pdf.cell(50, 10, 'Amount (KSh)', 1)
    pdf.cell(40, 10, 'Date', 1)
    pdf.ln()
    
    # Table Data
    pdf.set_font('Arial', '', 10)
    counter = 1
    for entry in entries:
        name = entry.sender_name or (f"Member {entry.sender_phone[-4:]}" if entry.sender_phone else "Member")
        pdf.cell(10, 10, str(counter), 1)
        pdf.cell(80, 10, name[:35], 1)
        pdf.cell(50, 10, f"{entry.amount:,.2f}", 1)
        pdf.cell(40, 10, entry.created_at.strftime("%Y-%m-%d"), 1)
        pdf.ln()
        counter += 1
        
    # Output to a byte string
    # FPDF output(dest='S') returns a latin1 string in fpdf1, or bytearray in fpdf2.
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    
    return base64.b64encode(pdf_bytes).decode('utf-8')
