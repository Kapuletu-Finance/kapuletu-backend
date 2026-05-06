# Dataset Generation & Testing Strategy

Creating a dataset of 3,000+ perfectly annotated examples might sound like it takes weeks of manual labor, but in modern NLP engineering, we automate 95% of the work. 

Here is the professional strategy for generating the data and splitting it into Training and Testing sets.

---

## Part 1: How to Generate 3,000+ Annotated Samples Quickly

We do not manually count characters for 3,000 messages. Instead, we use a combination of three professional techniques:

### Strategy 1: Programmatic Data Synthesis (The Fastest Way)
Since we know the standard structure of many M-Pesa and Bank messages, we can write a Python script to automatically generate fake messages. 
- **How it works**: The script takes a template: `"CODE Confirmed. You have received Ksh AMOUNT from SENDER on DATE."`
- It randomly injects a generated 10-character code, a random Kenyan name from a list of 500 names, and a random amount.
- **The Magic**: Because the Python script is building the string itself, it knows *exactly* where the characters were placed! It automatically calculates the `[start, end]` indexes and outputs perfect JSON instantly. We can generate 2,000 standard M-Pesa variations in 2 seconds.

### Strategy 2: LLM Bootstrapping (The Smartest Way for Real Data)
If you already have thousands of *real*, unannotated SMS messages sitting in your database, you can use a powerful LLM (like GPT-4o-mini or Gemini) as your unpaid intern.
- **How it works**: We write a quick script that loops through your real messages and asks the LLM: *"Find the exact start and end character indexes for the SENDER and AMOUNT in this text."*
- The LLM spits out the JSON coordinates. You then just quickly scroll through the generated JSON to ensure it looks correct.

### Strategy 3: UI-Based Manual Annotation (For the Tricky 5%)
For the highly complex, weirdly formatted, or heavily forwarded messages, automated tools might fail. 
- **How it works**: You upload these tricky messages to a free, open-source tool like **Doccano** or **Label Studio**. The tool provides a clean web UI where you literally just use your mouse to highlight the text. When you hit export, it generates the exact JSON file for you.

---

## Part 2: Training vs. Testing Datasets

You asked how we go about training and testing. In Machine Learning, you **must never** test the AI on the same data you used to train it. If you do, you don't know if the AI actually *learned* the patterns, or if it just *memorized* the answers.

Therefore, we split our data into two completely separate files:

### 1. `data/training_dataset.json` (The "Textbook" - 80% of data)
- **Size**: ~2,400 messages.
- **Purpose**: Used exclusively by `scripts/train_model.py`.
- **Function**: The AI studies these examples for hours to learn the grammar, patterns, and spatial relationships of the entities.

### 2. `data/testing_dataset.json` (The "Final Exam" - 20% of data)
- **Size**: ~600 messages.
- **Purpose**: Used exclusively by `scripts/test_parser.py`.
- **Function**: The AI has **never** seen these messages before. We feed the raw text to the AI and ask it to extract the data. We then write a script that compares the AI's answers against the hidden "Answer Key" in the JSON. If the AI scores 98%+, it is ready for production.

---

## Part 3: The Complete Execution Workflow & Required Files

To seamlessly merge your 500 real-world records with the synthetic data, we have created a fully automated infrastructure. Here are the exact files and the step-by-step process:

### The Required File Structure
1. **`data/real_world_annotated.json`**: This is where you will place your 500 real-world records. They represent the absolute "ground truth" of what actually happens in the field.
2. **`scripts/generate_synthetic_data.py`**: A python script that automatically generates thousands of synthetic records modeled *exactly* after the templates of the real-world data (so they are not out of scope).
3. **`data/synthetic_dataset.json`**: The output of the generation script.
4. **`scripts/split_dataset.py`**: The "Router". It takes the 500 real records + the synthetic records, merges them, shuffles them to remove bias, and splits them into the final Train/Test sets.
5. **`data/training_dataset.json`**: Output from the router (80% of data).
6. **`data/testing_dataset.json`**: Output from the router (20% of data).
7. **`scripts/test_parser.py`**: The Final Exam script that tests the trained model against the `testing_dataset.json`.

### The Step-by-Step Execution Process

**Step 1: Save Real Data**
Add your 500 real-world annotated records into `data/real_world_annotated.json`.

**Step 2: Generate Synthetic Data**
Run the generator script. This will create 1,000+ synthetic records that mimic the real ones to bulk up the AI's pattern recognition.
```bash
python scripts/generate_synthetic_data.py
```

**Step 3: Combine and Split (80/20)**
Run the dataset splitter. This script merges the real and synthetic files, shuffles them, and routes them to the final Train and Test JSON files.
```bash
python scripts/split_dataset.py
```

**Step 4: Train the AI**
Run the training script. It will read `data/training_dataset.json` and build your local SpaCy AI model.
```bash
python scripts/train_model.py
```

**Step 5: Administer the Final Exam**
Run the testing script. It evaluates the newly trained AI against the hidden `data/testing_dataset.json` and prints out exactly how well it predicted the amounts and names.
```bash
python scripts/test_parser.py
```

---

## Part 4: Testing & Output Validation

When you execute Step 5 (`scripts/test_parser.py`), the script performs two crucial validations to ensure you can trust the model before deploying it to production:

### 1. Deep Visual Inspection
Before calculating the mathematical score, the script outputs the first 5 parsed messages in a clean, human-readable format. This allows you to visually verify that the parsed fields (Sender, Amount, Code, etc.) map perfectly to the raw text.

```text
Message 1:
"UDLQC1OXZA Confirmed.You have received Ksh2,500.00 from DICKSON MWANIKI 0720000971 on 21/4/26"
Parsed Output Object:
  - Sender   : DICKSON MWANIKI
  - Amount   : 2500.0
  - Code     : UDLQC1OXZA
  - Provider : M-PESA
  - Date     : 2026-04-21T00:00:00
--------------------------------------------------
```

### 2. The Comprehensive Exam Mathematical Score
After the visual inspection, the script silently grades the remaining hundreds of messages in the testing dataset across **every single parameter**. It calculates independent accuracy scores for Amount, Code, Sender, Provider, Account, and Purpose, and then computes an overall system score.

It outputs a flexible, truthful analysis that explicitly tells you if the model is ready, or if it failed and why.

```text
============================================================
      🏆 KAPULETU AI COMPREHENSIVE EXAM RESULTS 🏆
============================================================
Total Messages Evaluated : 600
------------------------------------------------------------
AMOUNT          Accuracy :  100.0% (600/600 correct)
CODE            Accuracy :   99.5% (597/600 correct)
SENDER          Accuracy :   98.2% (589/600 correct)
PROVIDER        Accuracy :  100.0% (150/150 correct)
------------------------------------------------------------
OVERALL SYSTEM SCORE     :   99.4%
============================================================
🟢 PRODUCTION READY: Outstanding performance across all fields!
============================================================
```

If the model performs poorly (e.g., an overall score of 82%), the script will truthfully flag it as `🟡 ACCEPTABLE` or `🔴 CRITICAL FAILURE` and explicitly tell you to review the specific fields that are dragging the score down so you know exactly what kind of training data to add next.
