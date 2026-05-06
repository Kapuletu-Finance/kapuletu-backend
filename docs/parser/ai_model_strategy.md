# 🧠 Kapuletu AI: Transitioning to a Trainable Model (NER)

## 1. Concept: Rule-Based vs. Model-Based
- **Previous Approach**: Rule-based (Regex) + Memory (Fingerprints). Fast, but requires manual pattern definitions.
- **New Approach**: **Machine Learning (NER - Named Entity Recognition)**. The system is "fed" thousands of labeled messages and learns to identify 'SENDER', 'AMOUNT', and 'CODE' based on context and syntax, not just fixed positions.

## 2. The Training Pipeline
To achieve "101% accuracy" with high data volumes, we implement a training loop:

1.  **Data Collection**: Every message corrected by a Treasurer is saved as a **Labled Training Example**.
2.  **Model Training (Spacy/CRF)**: An offline process (or a heavier Lambda) reads these examples and trains a weights-based model.
3.  **Model Deployment**: The updated model (`model_v2.bin`) is pushed to the Ingestion Service, replacing the regex-heavy logic.

## 3. Revised AI Architecture
The `parser_engine.py` will now follow this logic:
1.  **Load Model**: Initialize the local Spacy/ML model.
2.  **Token Classification**: Scan tokens and assign labels (`SENDER`, `AMOUNT`).
3.  **Context Scoring**: Ensure the results make sense for a treasury context.

## 4. Implementation Steps for Massive Scale
| Phase | Action | Technology |
| :--- | :--- | :--- |
| **Data Labeling** | Export `pending_transactions` corrections | PostgreSQL -> JSONL |
| **Model Building** | Train a Custom NER Model | Spacy / Scikit-Learn |
| **Validation** | Verify against a test set (Hold-out data) | Precision/Recall Metrics |
| **Inference** | Load model in `parser_engine.py` | `spacy.load()` |

> [!IMPORTANT]
> To "train with huge data," we will provide a **Trainer Script** that consumes your historical message database and builds a proprietary model weights file. This file then lives inside your backend and delivers the "perfect" parsing you require.
