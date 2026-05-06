# SpaCy Dataset Annotation Guide

## 1. Overview
The `training_dataset.json` file serves as the "textbook" for your KapuLetu AI Parser. It provides the ground-truth examples that the SpaCy Named Entity Recognition (NER) model will study to understand the grammatical structure and layout of Kenyan financial messages.

The dataset is structured as a JSON Array (`[]`), where every object inside the array represents a single, independent transaction message.

---

## 2. The JSON Structure
Each transaction object requires exactly two fields: `"text"` and `"entities"`.

```json
{
  "text": "Ksh 300.00 sent to KCB account GRAPHICSPALACELTD 5848028 has been received on 24/04/2026 at 01:34 PM. M-PESA Ref UDORA1YWKR. To reverse this transaction, SMS this message to 16120.",
  "entities": [
    [4, 10, "AMOUNT"],
    [19, 22, "PROVIDER"],
    [31, 48, "SENDER"],
    [49, 56, "ACCOUNT"],
    [111, 121, "CODE"]
  ]
}
```

### A. The `"text"` Field
This is the raw, unedited string exactly as it arrives from the SMS or WhatsApp webhook. 
- **Rule of Thumb**: Do not clean or format this text before adding it to the dataset. If the real message contains typos, promotional spam, or weird date formats, leave them in! The AI must learn to navigate real-world noise.

### B. The `"entities"` Field (The Answer Key)
This field tells the AI exactly where the valuable data is hidden within the `"text"`. It is an array of coordinates (tuples). 

Each coordinate follows a strict 3-part format: 
`[start_character_index, end_character_index, "LABEL_NAME"]`

---

## 3. How Character Indexing Works
In Python and SpaCy, strings are treated as arrays of characters. The first character is at index `0`. 

Let's break down the `"entities"` from the example above to see exactly what we are teaching the AI:

1. **`[4, 10, "AMOUNT"]`**
   - If you count from `0`, the 4th character is the `3`, and the 10th character is the space after the last `0`.
   - The extracted string is exactly `"300.00"`.
2. **`[19, 22, "PROVIDER"]`**
   - The extracted string is exactly `"KCB"`.
3. **`[31, 48, "SENDER"]`**
   - The extracted string is exactly `"GRAPHICSPALACELTD"`.
4. **`[49, 56, "ACCOUNT"]`**
   - The extracted string is exactly `"5848028"`.
5. **`[111, 121, "CODE"]`**
   - The extracted string is exactly `"UDORA1YWKR"`.

*(Note: The `end_character_index` is **exclusive**, meaning it stops capturing right before that index number).*

---

## 4. Why Use Character Indexes? (The NLP Advantage)
You might wonder why we don't just provide a simple key-value pair like `{"CODE": "UDORA1YWKR"}`. 

We use exact character coordinates because we are training an AI to understand **spatial and contextual patterns**, not just memorizing values.

### Context Pattern Recognition
By seeing thousands of exact coordinates, the AI learns rules like:
> *"A 10-character alphanumeric `CODE` usually appears immediately following the phrase 'M-PESA Ref', OR it appears as the very first word in the sentence."*

Because it learns the *grammar* and *layout* surrounding the entity, you can feed the AI a completely new transaction message tomorrow, and it will instantly find the `CODE` based on the structural context.

### Ignoring the Noise
Notice how we **do not** highlight the promotional text, or instructions like *"To reverse this transaction..."*. 
Because we do not label those characters, the AI inherently learns to completely ignore promotional spam and irrelevant instructions. This makes the parser incredibly resilient against bank format updates or new marketing campaigns added to SMS receipts.


