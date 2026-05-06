# KapuLetu AI Parser Strategy

This document confirms the integration of the custom-trained AI model into the financial ingestion pipeline and outlines the roadmap for achieving 100% parsing accuracy.

---

## 🧠 1. The Core Engine: `kapuletu_ai_v1`

The intelligence of the system is centered around a custom-trained **SpaCy Named Entity Recognition (NER)** model located in:
`models/kapuletu_ai_v1/`

### How it is Used:
- **Priority Loading**: The `IngestionService` automatically attempts to load this specific model upon initialization.
- **Entity Extraction**: The model is trained to recognize four critical financial entities:
  - `SENDER`: The person or organization sending funds.
  - `AMOUNT`: The numerical value of the transaction.
  - `CODE`: The unique M-Pesa/Bank reference code.
  - `PURPOSE`: Contextual notes (e.g., "Welfare", "January Dues").

---

## 🛡️ 2. The "Safety-First" Architecture

To achieve the objective of **100% parsing accuracy**, we employ a hybrid strategy:

1.  **AI Model (Primary)**: Handles the heavy lifting of understanding unstructured language and context.
2.  **Heuristic Fallback (Safeguard)**: If the AI model has low confidence or encounters a format it hasn't seen yet, the system automatically triggers a set of high-precision regex patterns.
3.  **Treasurer Review**: All parsed data is stored in `pending_transactions`, allowing a human to verify and correct the AI's output before it is committed to the immutable ledger.

---

## 📈 3. Roadmap to 100% Accuracy

Achieving 100% accuracy is an iterative process:

### Data-Driven Training
As you ingest real-world messages, the system collects "Raw Message" vs "Corrected Data" pairs. This dataset is then used to:
- **Fine-tune the NER weights**.
- **Reduce false positives** in the extraction logic.

---

## ✅ Confirmation
I can confirm that the application is currently **wired to use the `models/kapuletu_ai_v1` model**. Every request processed through the `/ingestion` endpoint first attempts to use this AI Core before resorting to any other logic.
