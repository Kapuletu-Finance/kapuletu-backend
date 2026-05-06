# Real-World Dataset Analysis & Shape Report

## 1. Overview of Current Data
Before synthesizing 10,000+ records, we must deeply analyze the exact shape of our "ground truth"—the real-world data collected from your treasurers. This data dictates the patterns the AI must learn.

**Source**: `data/Training Data_1.xlsx`
**Current Extracted JSON**: `data/real_world_annotated.json`

## 2. The Shape of the Data (Volume & Distribution)
After running the extraction engine across the raw Excel file, here is the exact inventory of what we currently hold:

*   **Total Real-World Messages Extracted:** `99` messages
    *   *From M-Pesa Column:* `61` messages
    *   *From Provider Column:* `38` messages

### Parameter Annotation Coverage (The Target Fields)
The parser is expected to extract 6 primary fields: `CODE`, `AMOUNT`, `SENDER` (Who?), `DATE`, `PROVIDER`, and `ACCOUNT`. 
Here is how many of those fields were successfully auto-labeled across the 99 messages:

| Field | Auto-Annotated Count | Description / Observations |
| :--- | :--- | :--- |
| **CODE** | 95 | Excellent coverage. Almost every message contains a 10-character alphanumeric transaction reference. |
| **DATE** | 88 | Strong coverage. Real-world dates appear in multiple formats (e.g., `dd/mm/yy` vs `yyyy-mm-dd`). |
| **AMOUNT** | 75 | Good coverage. Some amounts were missing the standard `Ksh` or `KES` prefix in the raw text, requiring manual review. |
| **PROVIDER**| 196 | Over-indexed. Many messages mention the provider (like "KCB" or "M-PESA") multiple times in a single text. |
| **SENDER** | 6 | **POOR COVERAGE**. The Regex heuristic struggled to find the SENDER because real-world names are highly irregular. Some don't use "from", or the names are smashed together. |
| **ACCOUNT** | 4 | Low coverage. Most direct M-Pesa transfers don't use an account number, only Paybill/Till receipts do. |

---

## 3. Real-World Message Archetypes (The Templates)
By studying the 99 real-world messages, we identified the exact "Archetypes" (templates) that treasurers receive. **These exact archetypes will be used to generate the 10,000+ synthetic records.**

### Archetype A: Standard M-Pesa to M-Pesa (Direct)
> *"UDMP31RSCP Confirmed.You have received Ksh4,500.00 from PETER KINYANJUI 0712345678 on 22/4/26 at 2:34 PM..."*
*   **Target Fields**: `CODE`, `AMOUNT`, `SENDER`, `DATE`.

### Archetype B: Bank-to-Wallet / Wallet-to-Bank
> *"You have received KES 4500.0 from PETER KINYANJUI. M-PESA Ref UDMP31RSCP. Transaction Ref No DDM8FQCSHA"*
*   **Target Fields**: `AMOUNT`, `SENDER`, `CODE`, `PROVIDER`.

### Archetype C: Paybill / Buy Goods
> *"Ksh 300.00 sent to KCB account GRAPHICSPALACELTD 5848028 has been received on 24/04/2026 at 01:34 PM. M-PESA Ref UDORA1YWKR."*
*   **Target Fields**: `AMOUNT`, `PROVIDER`, `ACCOUNT` (Name/Number), `DATE`, `CODE`.

---

## 4. Path to 10,000+ Production Records
Because the current real-world data has low coverage for `SENDER` (due to complex formatting), we cannot just rely on regex for the real data. 

**Our Strategy:**
1. **Manual Review of the 99**: We must quickly manually review the 99 records in `real_world_annotated.json` to fix the missing `SENDER` tags so we have a perfect "Seed" dataset.
2. **The 10k Synthetic Engine**: The synthetic generator (`generate_synthetic_data.py`) will be upgraded to loop 10,000 times. It will strictly use Archetypes A, B, and C. Because the script generates the text, it will calculate the coordinates for `SENDER` with **100% mathematical accuracy**.
3. **The 80/20 Split**: We will mix the perfect 10,000 synthetic records with the 99 real ones, creating a highly robust 10,099 record dataset ready for professional training.

---

## 5. Identifying the SENDER Across Different Archetypes

Because treasurers receive messages from wildly different sources (Banks, M-Pesa, Forwarded texts), the `SENDER` is not always in the same place. Here is how we (and the AI) identify the SENDER structurally depending on the message type:

### 1. The "From" Trigger (Standard M-Pesa / Bank Drops)
In standard transfers, the SENDER's name immediately follows the word "from" and is usually terminated by a phone number, a date, or punctuation.
*   *Example:* "...received Ksh4,500.00 **from PETER KINYANJUI** 0712345678 on..."
*   *Identification Rule:* The AI learns to associate the preposition "from" + [AMOUNT] as the preceding context for a SENDER.

### 2. The "Account" Trigger (Paybill / Till Numbers)
When a treasurer receives a Paybill notification, there is no "from". Instead, the SENDER is often the name of the entity following the word "account".
*   *Example:* "...sent to KCB **account GRAPHICSPALACELTD** 5848028 has been..."
*   *Identification Rule:* The AI learns to look for the noun "account" or "acc" followed by an uppercase string as the SENDER/ACCOUNT entity.

### 3. Forwarded / Messy Triggers
When users manually forward messages, they often inject their own text or strip out formatting.
*   *Example:* *"Fwd: Payment **by JOHN DOE** for the contribution..."*
*   *Identification Rule:* The AI learns secondary prepositions like "by" or contextual cues like "Payment by" to locate the SENDER.

**Why SpaCy is Necessary:**
This variance is exactly why we use a Machine Learning Named Entity Recognition (NER) model instead of a simple script. A simple script breaks when a user types "acc" instead of "account". The SpaCy AI learns the *spatial context* (the words surrounding the SENDER) so it can intelligently adapt and find the name no matter how the message is formatted!
