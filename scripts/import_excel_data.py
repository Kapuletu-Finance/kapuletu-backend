import os
import json
import re
import logging
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEL_PATH = os.path.join(BASE_DIR, "data", "Training Data_1.xlsx")
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "real_world_annotated.json")

def bootstrap_annotations(text, provider_hint=""):
    """
    Intelligently guesses character coordinates for ALL parameters.
    """
    entities = []
    
    # 1. CODE (10 uppercase alphanumeric chars)
    code_match = re.search(r'\b([A-Z0-9]{10})\b', text)
    if code_match:
        entities.append([code_match.start(1), code_match.end(1), "CODE"])
        
    # 2. AMOUNT (Ksh or KES followed by digits)
    amt_match = re.search(r'(?:Ksh|KES)\s*([\d,]+\.?\d*)', text, re.IGNORECASE)
    if amt_match:
        entities.append([amt_match.start(1), amt_match.end(1), "AMOUNT"])
        
    # 3. DATE (dd/mm/yy or yyyy-mm-dd)
    date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})', text)
    if date_match:
        entities.append([date_match.start(1), date_match.end(1), "DATE"])
        
    # 4. SENDER ("from NAME" or "by NAME")
    sender_match = re.search(r'(?:from|by)\s+([A-Za-z\s]+)(?:\d{5,12}|\-|\.|\s(?:on|at|M-PESA|via|KCB))', text, re.IGNORECASE)
    if sender_match:
        sender_name = sender_match.group(1).strip()
        # Avoid matching generic words
        if len(sender_name) > 3 and sender_name.upper() not in ["KCB", "EQUITY"]:
            idx = text.find(sender_name, sender_match.start(1))
            entities.append([idx, idx + len(sender_name), "SENDER"])
            
    # 5. ACCOUNT (after "account" or "account no")
    acc_match = re.search(r'account(?:\s+no)?\s+([A-Z0-9\s]+?)(?:has\sbeen|\.)', text, re.IGNORECASE)
    if acc_match:
        acc_str = acc_match.group(1).strip()
        idx = text.find(acc_str, acc_match.start(1))
        entities.append([idx, idx + len(acc_str), "ACCOUNT"])

    # 6. PROVIDER (M-PESA, KCB, Equity, etc.)
    providers = ["KCB", "EQUITY", "M-PESA", "MPESA", "COOP", "AIRTEL", "ABSA", "NCBA"]
    if provider_hint and str(provider_hint).strip().lower() not in ('nan', 'none', ''):
        providers.append(str(provider_hint).strip().upper())
        
    for prov in set(providers):
        # Case insensitive find
        matches = re.finditer(re.escape(prov), text, re.IGNORECASE)
        for m in matches:
            entities.append([m.start(), m.end(), "PROVIDER"])

    # Resolve overlapping entities (SpaCy throws errors if coordinates overlap)
    entities.sort(key=lambda x: x[0])
    filtered_entities = []
    last_end = -1
    for ent in entities:
        if ent[0] >= last_end:
            filtered_entities.append(ent)
            last_end = ent[1]

    return filtered_entities

def import_and_bootstrap_excel():
    if not os.path.exists(EXCEL_PATH):
        logger.error(f"Excel file not found at {EXCEL_PATH}")
        return

    logger.info("Reading real-world Excel data...")
    df = pd.read_excel(EXCEL_PATH)
    
    # Identify columns flexibly to ensure we capture everything
    col_mpesa = next((c for c in df.columns if 'mpesa' in str(c).lower()), df.columns[0])
    col_bank = next((c for c in df.columns if 'provider' in str(c).lower() or 'bank' in str(c).lower()), df.columns[1] if len(df.columns) > 1 else None)
    col_plat = next((c for c in df.columns if 'platform' in str(c).lower()), df.columns[2] if len(df.columns) > 2 else None)

    dataset = []
    mpesa_count = 0
    bank_count = 0
    
    for index, row in df.iterrows():
        # Get raw text
        mpesa_msg = str(row[col_mpesa]).strip() if pd.notna(row[col_mpesa]) else ""
        bank_msg = str(row[col_bank]).strip() if col_bank and pd.notna(row[col_bank]) else ""
        provider_hint = str(row[col_plat]).strip() if col_plat and pd.notna(row[col_plat]) else ""
        
        if mpesa_msg and mpesa_msg.lower() not in ('nan', 'none', ''):
            dataset.append({
                "text": mpesa_msg,
                "entities": bootstrap_annotations(mpesa_msg, provider_hint)
            })
            mpesa_count += 1
            
        if bank_msg and bank_msg.lower() not in ('nan', 'none', ''):
            dataset.append({
                "text": bank_msg,
                "entities": bootstrap_annotations(bank_msg, provider_hint)
            })
            bank_count += 1

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, indent=2)

    logger.info("=" * 60)
    logger.info(f"✅ EXCEL IMPORT COMPLETE!")
    logger.info(f"Total Messages Extracted: {len(dataset)}")
    logger.info(f"  - M-Pesa Column   : {mpesa_count}")
    logger.info(f"  - Provider Column : {bank_count}")
    logger.info(f"All data intelligently mapped for: SENDER, AMOUNT, CODE, PROVIDER, ACCOUNT, and DATE.")
    logger.info("=" * 60)

if __name__ == "__main__":
    import_and_bootstrap_excel()
