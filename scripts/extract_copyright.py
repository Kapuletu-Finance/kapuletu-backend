import os
import re
import argparse
from datetime import datetime

# Configure the copyright header
COPYRIGHT_YEAR = datetime.now().year
COMPANY_NAME = "Kapuletu Systems"
COPYRIGHT_HEADER = f"""
/*******************************************************************************
 * Copyright (c) {COPYRIGHT_YEAR} {COMPANY_NAME}. All rights reserved.
 * 
 * This file is part of the proprietary source code of {COMPANY_NAME}.
 * Unauthorized copying, distribution, or use of this file, via any medium, 
 * is strictly prohibited.
 ******************************************************************************/

"""

# Basic patterns to flag for potential manual review (secrets, keys, etc.)
# This is a basic filter; always review the final output manually.
SECRET_PATTERNS = [
    re.compile(r'(?i)api[_-]?key\s*[:=]\s*[\'"][^\'"]+[\'"]'),
    re.compile(r'(?i)password\s*[:=]\s*[\'"][^\'"]+[\'"]'),
    re.compile(r'(?i)secret\s*[:=]\s*[\'"][^\'"]+[\'"]'),
    re.compile(r'(?i)token\s*[:=]\s*[\'"][^\'"]+[\'"]')
]

def format_file_for_submission(filepath):
    """Reads a file, prepends the copyright header, and flags potential secrets."""
    if not os.path.exists(filepath):
        print(f"[-] Error: File not found -> {filepath}")
        return None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"[-] Error reading {filepath}: {e}")
        return None

    # Check for potential secrets
    flags = []
    for i, line in enumerate(content.split('\n')):
        for pattern in SECRET_PATTERNS:
            if pattern.search(line):
                flags.append((i + 1, line.strip()))

    if flags:
        print(f"[!] WARNING: Potential secrets found in {filepath}:")
        for line_num, line_content in flags:
            print(f"    Line {line_num}: {line_content}")
        print("    Please redact these before finalizing your submission!")

    # Format the output block
    formatted_content = f"{'='*80}\n"
    formatted_content += f"FILE: {filepath}\n"
    formatted_content += f"{'='*80}\n"
    formatted_content += COPYRIGHT_HEADER
    formatted_content += content
    formatted_content += "\n\n"

    return formatted_content

def main():
    parser = argparse.ArgumentParser(description="Extract and format source code for copyright submission.")
    parser.add_argument('-i', '--input', required=True, help="Text file containing a list of file paths to extract (one per line).")
    parser.add_argument('-o', '--output', default='copyright_submission.txt', help="Output file name (default: copyright_submission.txt)")
    
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[-] Input list file not found: {args.input}")
        return

    print(f"[*] Reading file list from {args.input}...")
    with open(args.input, 'r', encoding='utf-8') as f:
        # Read lines, strip whitespace, ignore empty lines and comments
        file_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not file_list:
        print("[-] No files to process. Please add file paths to your input list.")
        return

    print(f"[*] Found {len(file_list)} files to process.")
    
    output_content = ""
    success_count = 0

    for filepath in file_list:
        formatted_block = format_file_for_submission(filepath)
        if formatted_block:
            output_content += formatted_block
            success_count += 1
            print(f"[+] Processed: {filepath}")

    # Write the final output document
    with open(args.output, 'w', encoding='utf-8') as out_f:
        out_f.write(output_content)

    print(f"\n[*] Done! Successfully processed {success_count}/{len(file_list)} files.")
    print(f"[*] Output saved to: {args.output}")
    print("[*] REMINDER: Always manually review the final output document to ensure no sensitive credentials or trade secrets are exposed.")

if __name__ == "__main__":
    main()
