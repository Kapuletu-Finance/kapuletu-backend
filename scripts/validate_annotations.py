import json
import random

with open(r"c:\Users\josep\kapuletu-backend\data\merged_annotated_dataset.json", "r", encoding="utf-8") as f:
    data = json.load(f)

errors = []
label_counts = {}

print(f"Total records to validate: {len(data)}")

for i, record in enumerate(data):
    text = record["text"]
    for start, end, label in record["entities"]:
        label_counts[label] = label_counts.get(label, 0) + 1
        extracted = text[start:end]
        
        # Check for leading/trailing spaces
        if extracted != extracted.strip():
            errors.append(f"Row {i}: Label {label} has leading/trailing spaces: '{extracted}'")
            
        if label == "CODE":
            if not extracted.isalnum():
                errors.append(f"Row {i}: CODE is not alphanumeric: '{extracted}'")
        elif label == "AMOUNT":
            # Strip commas and check if float
            try:
                float(extracted.replace(",", ""))
            except ValueError:
                errors.append(f"Row {i}: AMOUNT is not a valid number: '{extracted}'")

print("\n--- Label Counts ---")
for lbl, count in label_counts.items():
    print(f"{lbl}: {count}")

print(f"\nTotal Errors Found: {len(errors)}")
if errors:
    print("Sample Errors:")
    for err in errors[:10]:
        print(err)

print("\n--- Visual Inspection (Random Sample of 3) ---")
sample = random.sample(data, 3)
for record in sample:
    print(f"\nText: {record['text']}")
    for start, end, label in record["entities"]:
        print(f"  {label.ljust(10)}: '{record['text'][start:end]}'")

