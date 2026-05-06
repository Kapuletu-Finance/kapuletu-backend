# KapuLetu Parser Workflow & Dataset Guide

## 1. Overview
The KapuLetu Parser Engine is the core intelligence layer of the ingestion system. Its primary responsibility is to take highly varied, unstructured, and sometimes messy financial SMS or WhatsApp messages and accurately extract structured financial data (Amount, Sender, Reference Code, Date, Bank/Provider). 

Given that treasurers forward messages, receive automated bank receipts, and get standard M-Pesa alerts, the parser must be resilient and highly accurate to prevent financial discrepancies.

---

## 2. Full Parser Workflow
The parser operates in a multi-stage pipeline to guarantee 100% data integrity before hitting the database.

### Stage 1: Ingestion & Preprocessing
- **Capture**: A raw message string is received via the webhook (Twilio/WhatsApp/SMS).
- **Sanitization**: The system strips out invisible unicode characters, normalizes whitespace, and trims the message. 
- **Forwarding Detection**: Identifies prefixes like `Fwd:`, `Forwarded message:`, or quotation marks to understand the context of the sender versus the actual payer.

### Stage 2: Intent & Classification
- **Filtering**: The system quickly determines if the message is a valid financial transaction, a conversational message ("Hi treasurer"), or an outgoing payment (which might be irrelevant for collections).
- **Categorization**: Classifies the message source (e.g., Direct M-Pesa, KCB-to-Mpesa, Equity, Coop, Paybill Receipt).

### Stage 3: Local AI / Parsing Engine Extraction (The Core)
- The sanitized text is passed into your local AI model (e.g., the custom SpaCy NER model defined in `train_model.py`).
- **Extraction Targets**:
  - `amount`: Float (e.g., `10000.00`)
  - `sender_name`: String (e.g., `AMOS ILAVONGA SHIBUTSE`)
  - `sender_identifier`: String (Phone number, masked number `131****711`, or Account Number)
  - `transaction_reference`: String (e.g., `UDORA1YWKR`, `MBNHE744DPQ8YUO8`)
  - `transaction_date`: ISO 8601 Datetime
  - `provider`: String (e.g., `MPESA`, `KCB`, `EQUITY`)

### Stage 4: Strict Validation Layer
- **Rule-based Fallbacks**: Even with AI, we enforce deterministic rules. 
  - *Does the extracted reference match standard Kenyan financial formats? (e.g., 10 alphanumeric characters for M-Pesa).*
  - *Is the date in the future? (Reject/Flag).*
  - *Is the amount > 0?*

### Stage 5: Idempotency & Structuring
- **Deduplication**: Queries the database to check if `transaction_reference` already exists.
- **Output**: Returns a finalized, clean JSON object to be passed to the Persistence Layer (Database).

---

## 3. Dataset Documentation & Message Characteristics

To achieve professional accuracy, the model must be trained on a highly diverse dataset reflecting the real-world chaos of treasurer inboxes. 

### Key Message Categories & Characteristics

#### A. Bank-to-Wallet / Wallet-to-Bank Confirmations
These messages come directly from banks when a member deposits money into the group's bank account via M-Pesa.
- **Characteristics**: Usually contains a unique Bank Reference, an M-Pesa reference, masked phone numbers, and promotional text.
- **Example**: 
  > *MBNHE744DPQ8YUO8 Confirmed! You have received KES 10,000.00 from AMOS ILAVONGA SHIBUTSE - 131\*\*\*\*711 at 2026-04-01 10:45:18 AM via KCB. Pata extra cash with a flexible Mobile Loan of up to KES 300K. Dial \*522# or use the KCB App.*
- **Parsing Challenge**: Ignoring the promotional text ("Pata extra cash..."), extracting the masked number correctly, and identifying the bank (KCB).

#### B. Standard Paybill / Buy Goods Receipts
Messages received when a member pays directly to the group's Paybill or Till Number.
- **Characteristics**: Often clearly states the account name and number, has a standard format, but formats vary slightly based on whether it's a Paybill or Till.
- **Examples**:
  > *Ksh 300.00 sent to KCB account GRAPHICSPALACELTD 5848028 has been received on 24/04/2026 at 01:34 PM. M-PESA Ref UDORA1YWKR. To reverse this transaction, SMS this message to 16120.*
  > 
  > *Ksh 660.00 sent to KCB account GRAPHICSPALACELTD 5848028 has been received on 24/04/2026 at 04:58 PM. M-PESA Ref UDORA1ZJE2. To reverse this transaction, SMS this message to 16120.*
- **Parsing Challenge**: Mapping the "account" to the internal project/group, parsing DD/MM/YYYY formats correctly into ISO datetimes.

#### C. Treasurer "Forwarded" Messages
Members often pay via their own phones and forward the M-Pesa confirmation SMS to the Treasurer via WhatsApp or SMS.
- **Characteristics**: Prepended with forwarding artifacts, dates might be relative or embedded inside the forwarded block.
- **Example**:
  > *[Forwarded] QED34XYZ98 Confirmed. You have sent Ksh 500 to KAPULETU WELFARE...*
- **Parsing Challenge**: Reversing the perspective. The message says "You have sent", but from the Treasurer's perspective, the group *received* the money. The sender is the person who forwarded it (or the name in the message).

#### D. Direct M-Pesa P2P Receipts (Treasurer's Personal Phone)
If a treasurer is using their personal number to collect funds.
- **Characteristics**: Standard "You have received..."
- **Example**: 
  > *PK12345678 Confirmed. You have received Ksh 1,500.00 from JANE DOE 0712345678 on 12/10/25 at 9:00 AM. New M-PESA balance is Ksh 12,500.00.*
- **Parsing Challenge**: Dropping the "New M-PESA balance" to avoid confusing it with the transaction amount.

---

## 4. Dataset Size & Structure Recommendations

To train your custom Local NLP Model (like your SpaCy Named Entity Recognition model) to professional standards, you need a high-quality, perfectly annotated dataset.

### A. Recommended Dataset Sizes for Professional Accuracy (>99.5%)

| Dataset Phase | Recommended Size | Description |
| :--- | :--- | :--- |
| **Minimum Viable (MVP)** | 500 - 1,000 samples | Good for initial validation. Catches 90% of standard messages. |
| **Production Training (Train)** | 3,000 - 5,000 samples | Required for training a robust, production-ready local model (SpaCy). Ensures the model learns edge cases, promo text ignoring, and varying date formats natively. |
| **Professional Testing (Test)** | 500 - 1,000 samples | A held-out dataset strictly used to benchmark the model. Must contain at least 20% "tricky" edge cases (e.g., forwarded messages, weird bank promos). |

### B. Distribution of the Dataset
To ensure the model isn't biased, the training data must mirror real-world variance:
- **40%** Standard M-Pesa Paybill/Till receipts.
- **30%** Bank-to-Wallet Confirmations (KCB, Equity, Coop, Absa).
- **15%** Forwarded Messages (with WhatsApp/SMS forwarding artifacts).
- **10%** Direct P2P M-Pesa receipts.
- **5%** "Noise / Negative Examples" (Promotional spam, conversational messages like "Hi I paid", where the model should output `null` or `invalid`).

### C. Format of the SpaCy JSON Dataset
Your local script (`scripts/train_model.py`) expects the dataset to be in a standardized JSON array format. Each object must contain the raw `text` and an array of `entities` identifying the exact start character index, end character index, and the label.

```json
[
  {
    "text": "UDLQC1OXZA Confirmed.You have received Ksh2,500.00 from DICKSON MWANIKI 0720000971 on 21/4/26",
    "entities": [
      [0, 10, "CODE"],
      [44, 49, "AMOUNT"],
      [55, 70, "SENDER"]
    ]
  }
]
```

### D. How to Create the Dataset
1. **Manual JSON Authoring**: You can manually write/edit the `data/training_dataset.json` file. Use a character counting tool (or Python `len()`) to find the exact start and end indexes for each entity.
2. **Using an Annotation UI (Recommended)**: For a professional workflow, use an open-source text annotation tool like **Doccano** or **Label Studio**. You upload your raw messages, highlight the text visually to tag SENDER, AMOUNT, etc., and then export the results directly into JSON.
3. **Automated Bootstrapping (Scripting)**: Write a quick Python script using basic Regex (or an offline AI) to auto-guess the indexes of codes and amounts for thousands of messages, save it to `training_dataset.json`, and then manually correct the mistakes.

## 5. Next Steps for Implementation
1. **Data Collection**: Gather raw M-Pesa/Bank messages into a text file or spreadsheet.
2. **Annotation**: Format them into the JSON structure shown above and save as `data/training_dataset.json`. (A starter file has already been created for you).
3. **Model Training**: Run `python scripts/train_model.py`. The script is now configured to dynamically load your JSON file. It also supports importing professional Spacy base models (like `en_core_web_md`).
4. **Evaluation**: Build an evaluation script (`scripts/test_parser.py`) to benchmark the accuracy before deploying to production.
