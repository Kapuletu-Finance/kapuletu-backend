import random
import os

files_to_merge = [
    'give-to.txt',
    'paid-to.txt',
    'providers-receipts.txt',
    'received-messages.txt',
    'sent-to.txt'
]

base_dir = r"c:\Users\josep\kapuletu-backend\data"
all_lines = []

for filename in files_to_merge:
    filepath = os.path.join(base_dir, filename)
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
            all_lines.extend(lines)

random.shuffle(all_lines)

output_path = os.path.join(base_dir, 'merged_training_data.txt')
with open(output_path, 'w', encoding='utf-8') as f:
    for line in all_lines:
        f.write(line + "\n")

print(f"Merged and shuffled {len(all_lines)} lines into merged_training_data.txt")
