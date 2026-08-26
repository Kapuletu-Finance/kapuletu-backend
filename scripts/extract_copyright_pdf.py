import os
import re
import argparse
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak, Preformatted
from reportlab.lib.units import inch
from reportlab.lib import colors

# Configuration
COPYRIGHT_YEAR = datetime.now().year
COMPANY_NAME = "Kapuletu Systems"
LOGO_PATH = os.path.join("assets", "logo.jpg")

SECRET_PATTERNS = [
    re.compile(r'(?i)api[_-]?key\s*[:=]\s*[\'"][^\'"]+[\'"]'),
    re.compile(r'(?i)password\s*[:=]\s*[\'"][^\'"]+[\'"]'),
    re.compile(r'(?i)secret\s*[:=]\s*[\'"][^\'"]+[\'"]'),
    re.compile(r'(?i)token\s*[:=]\s*[\'"][^\'"]+[\'"]')
]

def header_footer(canvas, doc):
    canvas.saveState()
    
    # Draw header with logo
    header_y = doc.pagesize[1] - 0.75 * inch
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(inch, header_y, "Kapuletu Systems - Copyright Submission Document")
    canvas.setFont("Helvetica", 9)
    canvas.drawString(inch, header_y - 15, "Proprietary & Confidential")
    
    # Optional: draw logo in top right if it exists
    if os.path.exists(LOGO_PATH):
        try:
            # We scale the logo roughly to fit in a 1-inch box
            canvas.drawImage(LOGO_PATH, doc.pagesize[0] - 2*inch, header_y - 15, width=1*inch, height=1*inch, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
            
    # Draw footer
    footer_y = 0.5 * inch
    canvas.setFont("Helvetica", 9)
    canvas.drawString(inch, footer_y, f"© {COPYRIGHT_YEAR} {COMPANY_NAME}. All rights reserved.")
    page_num = f"Page {doc.page}"
    canvas.drawRightString(doc.pagesize[0] - inch, footer_y, page_num)
    
    # Add a thin line above footer and below header
    canvas.setStrokeColor(colors.grey)
    canvas.line(inch, header_y - 20, doc.pagesize[0] - inch, header_y - 20)
    canvas.line(inch, footer_y + 10, doc.pagesize[0] - inch, footer_y + 10)
    
    canvas.restoreState()


def get_file_content_and_check(filepath):
    """Reads a file and flags potential secrets."""
    if not os.path.exists(filepath):
        print(f"[-] Error: File not found -> {filepath}")
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"[-] Error reading {filepath}: {e}")
        return None

    flags = []
    for i, line in enumerate(content.split('\n')):
        for pattern in SECRET_PATTERNS:
            if pattern.search(line):
                flags.append((i + 1, line.strip()))

    if flags:
        print(f"[!] WARNING: Potential secrets found in {filepath}:")
        for line_num, line_content in flags:
            print(f"    Line {line_num}: {line_content}")
        print("    Please redact these before submitting!")
    
    return content

def main():
    parser = argparse.ArgumentParser(description="Extract and generate a PDF for copyright submission.")
    parser.add_argument('-i', '--input', required=True, help="Text file containing a list of file paths to extract (one per line).")
    parser.add_argument('-o', '--output', default='copyright_submission.pdf', help="Output PDF file name (default: copyright_submission.pdf)")
    
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[-] Input list file not found: {args.input}")
        return

    print(f"[*] Reading file list from {args.input}...")
    with open(args.input, 'r', encoding='utf-8') as f:
        file_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not file_list:
        print("[-] No files to process. Please add file paths to your input list.")
        return
        
    print(f"[*] Found {len(file_list)} files to process.")
    
    doc = SimpleDocTemplate(
        args.output,
        pagesize=letter,
        rightMargin=inch, leftMargin=inch,
        topMargin=1.2*inch, bottomMargin=inch
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        textColor=colors.HexColor("#1e3a8a"),
        alignment=1 # Center
    )
    
    file_title_style = ParagraphStyle(
        'FileTitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.HexColor("#b91c1c")
    )
    
    # Monospaced font for code
    code_style = ParagraphStyle(
        'CodeStyle',
        parent=styles['Code'],
        fontSize=8,
        leading=10,
        leftIndent=0,
        rightIndent=0,
        wordWrap='CJK', # Simple wrap
        textColor=colors.black
    )

    story = []

    # Title Page
    story.append(Spacer(1, 2*inch))
    if os.path.exists(LOGO_PATH):
        try:
            logo = RLImage(LOGO_PATH, width=2.5*inch, height=2.5*inch, preserveAspectRatio=True)
            story.append(logo)
            story.append(Spacer(1, 0.5*inch))
        except Exception as e:
            pass
            
    story.append(Paragraph("Software Source Code Registration", title_style))
    story.append(Paragraph(f"<b>Company:</b> {COMPANY_NAME}", styles['Normal']))
    story.append(Paragraph(f"<b>Date Generated:</b> {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("<b>CONFIDENTIAL AND PROPRIETARY</b>", styles['Normal']))
    story.append(Paragraph("This document contains unpublished, proprietary source code of Kapuletu Systems. It is provided strictly for the purpose of copyright registration and may not be reproduced or distributed.", styles['Normal']))
    
    story.append(PageBreak())

    # Code Blocks
    success_count = 0
    for filepath in file_list:
        content = get_file_content_and_check(filepath)
        if content:
            # File Header
            story.append(Paragraph(f"File: {filepath}", file_title_style))
            
            # Code Content using Preformatted to keep whitespace/indentation
            story.append(Preformatted(content, code_style))
            story.append(PageBreak())
            success_count += 1
            print(f"[+] Processed: {filepath}")

    print(f"[*] Building PDF (this may take a moment)...")
    try:
        doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
        print(f"\n[*] Done! Successfully processed {success_count}/{len(file_list)} files.")
        print(f"[*] Output saved to: {args.output}")
    except Exception as e:
        print(f"[-] Failed to generate PDF: {e}")

if __name__ == "__main__":
    main()
