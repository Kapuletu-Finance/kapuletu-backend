# Module: AI Parser Governance

## 1. Overview
The KapuLetu AI Parser (the "Brain") is responsible for turning unstructured WhatsApp/SMS messages into finalized financial transactions. This module allows admins to manage the health, accuracy, and continuous learning of the NLP engine.

## 2. Key Functionalities

### 2.1 Model Training Management
Admins control the lifecycle of the SpaCy NER (Named Entity Recognition) model.
- **Training Trigger**: Initiating a new training run via `scripts/train_model.py`.
- **Performance Metrics**: Monitoring training loss and validation accuracy (F1 score, Precision, Recall).
- **Model Versioning**: Keeping a history of model weights and allowing a "rollback" if a new model performs poorly in production.

### 2.2 Knowledge Base Oversight
Managing the `ParserKnowledge` database of message fingerprints.
- **Fingerprint Review**: Viewing the most common message structures being ingested.
- **Pattern Merging**: Combining similar fingerprints to reduce noise and improve matching logic.
- **Pruning**: Removing old or inaccurate fingerprints that lead to parsing errors.

### 2.3 Real-time Training Feedback Loop
The most critical feature for "Professional Grade" accuracy is the human-in-the-loop system.
- **Correction Capture**: When a Treasurer manually edits an "Amount" or "Sender" during the approval flow, the system flags this as a "Correction Event."
- **Feedback Queue**: These corrections are reviewed by admins and automatically converted into new training samples (JSON) for the next model iteration.
- **Confidence Scoring**: Adjusting the thresholds at which the AI automatically trusts a parse versus requiring manual treasurer review.

### 2.4 Hyperparameter Control
Fine-tuning the training process without code changes.
- **Epochs**: Number of training iterations.
- **Dropout**: The "forgetting rate" that prevents the model from just memorizing the data.
- **Batch Size**: How many samples are processed at once.

## 3. Data Captured for Auditing
- **Action**: (e.g., `MODEL_TRAINED`, `FINGERPRINT_UPDATED`).
- **Entity**: Model version or fingerprint ID.
- **Payload**: Loss values, training time, and new parameters.

## 4. Operational Workflow
1. **Ingestion**: AI parses a message.
2. **Correction**: Treasurer corrects a mistake.
3. **Capture**: System saves the correction.
4. **Review**: Admin approves the correction as a training sample.
5. **Re-train**: Admin triggers a new model build.
6. **Deploy**: New model is moved to production.

---
**Technical Note**: The underlying training logic is located in `scripts/train_model.py` and uses the datasets in `data/training_dataset.json`.
