import os
import json
import pandas as pd
from typing import List, Dict

DATA_DIR = r"c:\Users\josep\kapuletu-backend\data"
OUTPUT_DIR = DATA_DIR

def extract_entities(text: str, entities: List[List]) -> Dict[str, str]:
    extracted = {}
    for start, end, label in entities:
        entity_text = text[start:end].strip()
        if label in extracted:
            extracted[label] = f"{extracted[label]}; {entity_text}"
        else:
            extracted[label] = entity_text
    return extracted

def json_to_excel(json_filename: str, excel_filename: str):
    json_path = os.path.join(DATA_DIR, json_filename)
    excel_path = os.path.join(OUTPUT_DIR, excel_filename)
    
    if not os.path.exists(json_path):
        print(f"Skipping {json_filename}: File not found.")
        return

    print(f"Converting {json_filename} to {excel_filename}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    rows = []
    for entry in data:
        text = entry.get('text', '')
        entities = entry.get('entities', [])
        row = {'Original Text': text}
        extracted = extract_entities(text, entities)
        row.update(extracted)
        rows.append(row)
    
    df = pd.DataFrame(rows)
    # Reorder columns to have common ones first
    common_cols = ['Original Text', 'CODE', 'DATE', 'AMOUNT', 'SENDER', 'PROVIDER', 'ACCOUNT']
    cols = [c for c in common_cols if c in df.columns]
    remaining = [c for c in df.columns if c not in common_cols]
    df = df[cols + remaining]
    
    df.to_excel(excel_path, index=False)
    print(f"Saved {len(df)} rows to {excel_filename}")

def txt_to_excel(txt_filenames: List[str], excel_filename: str):
    excel_path = os.path.join(OUTPUT_DIR, excel_filename)
    all_rows = []
    
    for filename in txt_filenames:
        txt_path = os.path.join(DATA_DIR, filename)
        if not os.path.exists(txt_path):
            print(f"Skipping {filename}: File not found.")
            continue
            
        print(f"Reading {filename}...")
        with open(txt_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            for line in lines:
                all_rows.append({'Source File': filename, 'Text': line})
                
    if all_rows:
        df = pd.DataFrame(all_rows)
        df.to_excel(excel_path, index=False)
        print(f"Saved {len(df)} rows to {excel_filename}")

if __name__ == "__main__":
    # JSON Datasets
    json_files = {
        'training_dataset.json': 'Official_Training_Dataset.xlsx',
        'testing_dataset.json': 'Official_Testing_Dataset.xlsx',
        'synthetic_dataset.json': 'Official_Synthetic_Dataset.xlsx',
        'real_world_annotated.json': 'Official_Real_World_Dataset.xlsx',
        'merged_annotated_dataset.json': 'Official_Merged_Dataset.xlsx'
    }
    
    for j_file, e_file in json_files.items():
        json_to_excel(j_file, e_file)
        
    # Text Datasets
    txt_files = [
        'give-to.txt',
        'paid-to.txt',
        'providers-receipts.txt',
        'received-messages.txt',
        'sent-to.txt',
        'demo_messages.txt'
    ]
    txt_to_excel(txt_files, 'Official_Raw_Messages_Dataset.xlsx')

    print("\nAll conversions completed!")
