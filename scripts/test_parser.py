import sys
import os
import json
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ingestion.parser_engine import parse_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DATA_PATH = os.path.join(BASE_DIR, "data", "testing_dataset.json")

def test_parser():
    """
    Test Utility: Validates the AI Parsing Engine against the held-out testing dataset.
    This performs a deep, comprehensive exam analysis across ALL extracted entities.
    """
    if not os.path.exists(TEST_DATA_PATH):
        logger.error(f"Testing dataset not found at {TEST_DATA_PATH}. Run split_dataset.py first.")
        sys.exit(1)
        
    with open(TEST_DATA_PATH, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)
        
    total_cases = len(test_cases)
    if total_cases == 0:
        logger.error("Testing dataset is empty.")
        return

    logger.info(f"Administering Comprehensive Final Exam: Testing against {total_cases} unseen messages...")
    
    # Dictionary to track performance across all entity types
    metrics = {
        "AMOUNT": {"correct": 0, "total": 0},
        "CODE": {"correct": 0, "total": 0},
        "SENDER": {"correct": 0, "total": 0},
        "PROVIDER": {"correct": 0, "total": 0},
        "ACCOUNT": {"correct": 0, "total": 0},
        "PURPOSE": {"correct": 0, "total": 0}
    }

    print("\n" + "="*80)
    print("      --- VISUAL INSPECTION (First 10 Real-World Messages) ---")
    print("="*80)

    for i, case in enumerate(test_cases):
        msg = case["text"]
        entities = case.get("entities", [])
        
        # Extract ground truth into a dictionary: {"AMOUNT": "500", "SENDER": "JOHN"}
        expected = {}
        for start, end, label in entities:
            expected[label] = msg[start:end].strip()
                
        # Ask the AI to predict
        result = parse_message(msg)
        
        # Grade EVERY expected label found in the json answer key
        for label, exp_val in expected.items():
            if label not in metrics:
                metrics[label] = {"correct": 0, "total": 0}
                
            metrics[label]["total"] += 1
            
            # Mathematical evaluation logic based on entity type
            if label == "AMOUNT":
                import re
                # Strip out 'Ksh', 'KES', commas, and whitespace to extract the raw number
                exp_amt = re.sub(r"[^\d.]", "", exp_val)
                if exp_amt.count(".") > 1:
                    parts = exp_amt.split(".")
                    exp_amt = "".join(parts[:-1]) + "." + parts[-1]
                pred_amt = result.get("amount", 0.0)
                try:
                    if float(exp_amt) == float(pred_amt):
                        metrics[label]["correct"] += 1
                except ValueError:
                    pass
                    
            elif label == "CODE":
                pred_code = result.get("transaction_code", "")
                if pred_code and exp_val.upper() == str(pred_code).upper():
                    metrics[label]["correct"] += 1
                    
            elif label == "SENDER":
                pred_sender = result.get("sender_name", "")
                # Allow partial matches for names since middle names might drop
                if pred_sender and str(pred_sender).upper() in exp_val.upper():
                    metrics[label]["correct"] += 1
                    
            elif label == "PROVIDER":
                pred_provider = result.get("provider", "")
                if pred_provider and exp_val.upper() in str(pred_provider).upper():
                    metrics[label]["correct"] += 1
                    
            elif label == "DATE":
                pred_date = result.get("transaction_date", "")
                if pred_date and exp_val.upper() == str(pred_date).upper():
                    metrics[label]["correct"] += 1
                    
            else:
                # Catch-all for ACCOUNT, PURPOSE, etc.
                pred_val = result.get(label.lower(), "")
                if pred_val and exp_val.upper() == str(pred_val).upper():
                    metrics[label]["correct"] += 1

        # Print the first 10 samples for deep visual inspection (Guaranteed to be real data)
        if i < 10:
            print(f"\nMessage {i+1}:")
            print(f"\"{msg}\"")
            print("Parsed Output Object:")
            print(f"  - Sender   : {result.get('sender_name')}")
            print(f"  - Amount   : {result.get('amount')}")
            print(f"  - Code     : {result.get('transaction_code')}")
            print(f"  - Provider : {result.get('provider', 'N/A')}")
            print(f"  - Date     : {result.get('transaction_date', 'N/A')}")
            print("-" * 50)

    if total_cases > 10:
        print(f"\n... and {total_cases - 10} more messages parsed and graded silently in the background.")
    print("="*80)

    # Calculate final comprehensive accuracy percentages
    print("\n" + "="*60)
    print("      --- KAPULETU AI COMPREHENSIVE EXAM RESULTS ---")
    print("="*60)
    print(f"Total Messages Evaluated : {total_cases}")
    print("-" * 60)
    
    total_correct = 0
    total_tested = 0
    
    # Print metrics dynamically only for labels that were actually tested
    for label, data in metrics.items():
        if data["total"] > 0:
            accuracy = (data["correct"] / data["total"]) * 100
            print(f"{label:<15} Accuracy : {accuracy:6.1f}% ({data['correct']}/{data['total']} correct)")
            total_correct += data["correct"]
            total_tested += data["total"]
            
    print("-" * 60)
    overall_accuracy = (total_correct / total_tested * 100) if total_tested > 0 else 0.0
    print(f"OVERALL SYSTEM SCORE   : {overall_accuracy:6.1f}%")
    print("="*60)
    
    # Strict truthful analysis
    if overall_accuracy >= 98.0:
        print("[PASS] PRODUCTION READY: Outstanding performance across all fields!")
    elif overall_accuracy >= 90.0:
        print("[WARN] ACCEPTABLE: Model is viable, but some specific fields (e.g., SENDER) may be dragging the score down. Review logs.")
    elif overall_accuracy >= 75.0:
        print("[FAIL] POOR PERFORMANCE: Model is missing key parameters. It has likely overfitted or needs more edge-case training data.")
    else:
        print("[CRITICAL] CRITICAL FAILURE: Accuracy is unacceptable for financial data. Do NOT deploy. Rebuild dataset.")
        
    print("="*60 + "\n")

if __name__ == "__main__":
    test_parser()
