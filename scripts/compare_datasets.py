import json
import os

def analyze_dataset(file_path):
    if not os.path.exists(file_path):
        return None
        
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    labels = set()
    total_entities = 0
    
    for record in data:
        for start, end, label in record.get("entities", []):
            labels.add(label)
            total_entities += 1
            
    return {
        "size": len(data),
        "labels": sorted(list(labels)),
        "total_entities": total_entities,
        "sample": data[0] if data else None
    }

base_dir = r"c:\Users\josep\kapuletu-backend\data"
files = {
    "Existing Training": "training_dataset.json",
    "Existing Testing": "testing_dataset.json",
    "New Merged Annotated": "merged_annotated_dataset.json"
}

for name, filename in files.items():
    path = os.path.join(base_dir, filename)
    stats = analyze_dataset(path)
    if stats:
        print(f"--- {name} ({filename}) ---")
        print(f"Total Records: {stats['size']}")
        print(f"Unique Labels Used: {stats['labels']}")
        print(f"Total Entities: {stats['total_entities']}")
        if stats['sample']:
            print(f"Sample Structure: Keys -> {list(stats['sample'].keys())}")
            # print(f"Sample Data: {stats['sample']}")
        print()
    else:
        print(f"--- {name} ({filename}) ---")
        print("FILE NOT FOUND\n")
