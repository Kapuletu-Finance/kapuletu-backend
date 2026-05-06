import os
import json
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

REAL_WORLD_PATH = os.path.join(DATA_DIR, "real_world_annotated.json")
SYNTHETIC_PATH = os.path.join(DATA_DIR, "synthetic_dataset.json")
MERGED_ANNOTATED_PATH = os.path.join(DATA_DIR, "merged_annotated_dataset.json")
TRAIN_OUTPUT_PATH = os.path.join(DATA_DIR, "training_dataset.json")
TEST_OUTPUT_PATH = os.path.join(DATA_DIR, "testing_dataset.json")

def load_json_safe(filepath):
    if not os.path.exists(filepath):
        logger.warning(f"File not found: {filepath}. Skipping.")
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def combine_and_split(train_ratio=0.8):
    """
    Combines real-world data and synthetic data, shuffles them to prevent bias,
    and splits them into an 80% Training set and a 20% Testing set.
    """
    # 1. Load Datasets
    logger.info("Loading datasets...")
    real_data = load_json_safe(REAL_WORLD_PATH)
    synth_data = load_json_safe(SYNTHETIC_PATH)
    merged_data = load_json_safe(MERGED_ANNOTATED_PATH)
    
    # Extract 10 real samples to guarantee they are the ones printed in the final visual exam
    if len(real_data) >= 10:
        reserved_real = real_data[:10]
        remaining_real = real_data[10:]
    else:
        logger.warning("Less than 10 real samples available.")
        reserved_real = real_data[:]
        remaining_real = []

    combined_data = remaining_real + synth_data + merged_data
    total = len(combined_data) + len(reserved_real)
    
    if total == 0:
        logger.error("No data found! Run generate_synthetic_data.py first or add real_world_annotated.json.")
        return
        
    logger.info(f"Combined {len(real_data)} real, {len(synth_data)} synthetic, and {len(merged_data)} new merged records. Total: {total}")
    
    # 2. Shuffle to ensure model doesn't learn ordering bias
    random.shuffle(combined_data)
    
    # 3. Calculate Split
    split_index = int(len(combined_data) * train_ratio)
    train_data = combined_data[:split_index]
    test_data = combined_data[split_index:]
    
    # Guarantee that the first 10 items in the test data are REAL WORLD samples (unseen by AI)
    test_data = reserved_real + test_data
    
    # 4. Save to Disk
    with open(TRAIN_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(train_data, f, indent=2)
        
    with open(TEST_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, indent=2)
        
    logger.info(f"Split Complete! Training Set: {len(train_data)} records. Testing Set: {len(test_data)} records.")
    logger.info(f"Saved to: {TRAIN_OUTPUT_PATH} and {TEST_OUTPUT_PATH}")
    logger.info("Next Step: Run 'python scripts/train_model.py'")

if __name__ == "__main__":
    combine_and_split()
