import os
import sys
import json
import logging
import spacy
from spacy.tokens import DocBin
from spacy.util import filter_spans

# Configuration: Automatic Path Resolution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_OUTPUT_DIR = os.path.join(BASE_DIR, "models", "kapuletu_ai_v1")
DATASET_PATH = os.path.join(BASE_DIR, "data", "training_dataset.json")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# DYNAMIC DATASET LOADING
def load_dataset(filepath):
    """Loads the training dataset from the standardized JSON format."""
    if not os.path.exists(filepath):
        logger.error(f"Dataset not found at {filepath}. Please create it to proceed.")
        sys.exit(1)
        
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
        
    logger.info(f"Loaded {len(raw_data)} samples from {filepath}")
    train_data = []
    for item in raw_data:
        # Convert JSON structure to SpaCy tuple format: ("text", {"entities": [(start, end, "LABEL")]})
        entities = [(ent[0], ent[1], ent[2]) for ent in item.get("entities", [])]
        train_data.append((item["text"], {"entities": entities}))
        
    return train_data

TRAIN_DATA = load_dataset(DATASET_PATH)

def train_and_save_model():
    """
    NLP Training Suite: Generates custom weights for the SpaCy NER engine.
    
    This script is the 'Brain Builder' of KapuLetu. It takes raw text samples
    and their corresponding entity labels (SENDER, AMOUNT, etc.) to create 
    a statistical model that can understand unstructured financial messages.
    
    Workflow:
    1. Infrastructure: Resolves paths and prepares the output directory.
    2. Initialization: Bootstraps a blank English NLP pipeline.
    3. Labeling: Registers the specific financial entities we want to track.
    4. Transformation: Converts the 'TRAIN_DATA' list into a high-performance binary 'DocBin'.
    5. Deployment: Saves the resulting model directly into the 'models/' directory
       where it is immediately picked up by the Parser Engine.
    """
    logger.info("KapuLetu AI Core: Initiating high-accuracy training pipeline...")

    # 1. Initialize Model
    # Choose whether to start from scratch or build upon a professional pre-trained base model.
    # To use a professional base model, set this to e.g., "en_core_web_md" or "en_core_web_trf".
    # (Note: you must install the base model first: `python -m spacy download en_core_web_md`)
    base_model = None 
    
    if base_model:
        logger.info(f"Loading professional base model: {base_model}")
        nlp = spacy.load(base_model)
    else:
        logger.info("Initializing a fast, lightweight blank English model.")
        nlp = spacy.blank("en")
    if "ner" not in nlp.pipe_names:
        ner = nlp.add_pipe("ner")
    else:
        ner = nlp.get_pipe("ner")

    # 2. Register Labels
    # Tell the model what categories it needs to learn.
    for _, annotations in TRAIN_DATA:
        for ent in annotations.get("entities"):
            ner.add_label(ent[2])

    # 3. Process Data into binary format
    # DocBin is SpaCy's optimized format for serializing training documents.
    db = DocBin()
    for text, annot in TRAIN_DATA:
        doc = nlp.make_doc(text)
        ents = []
        for start, end, label in annot["entities"]:
            # Map character spans to the document tokens
            span = doc.char_span(start, end, label=label)
            if span:
                ents.append(span)
        # Handle overlapping spans if any (Safety First)
        doc.ents = filter_spans(ents)
        db.add(doc)

    # 4. Perform Training
    import random
    from spacy.training.example import Example
    
    logger.info("Starting deep learning training loop (10 Epochs)...")
    optimizer = nlp.begin_training()
    
    # Train for 10 iterations
    for itn in range(10):
        random.shuffle(TRAIN_DATA)
        losses = {}
        # Batch up the examples using spaCy's minibatch
        batches = spacy.util.minibatch(TRAIN_DATA, size=8)
        for batch in batches:
            examples = []
            for text, annotations in batch:
                doc = nlp.make_doc(text)
                # Create an Example object (required for spaCy 3.x)
                example = Example.from_dict(doc, annotations)
                examples.append(example)
                
            # Update the model with the batch
            nlp.update(
                examples,  
                drop=0.2,  # Dropout - makes it harder to memorise data
                sgd=optimizer, # Stochastic gradient descent
                losses=losses,
            )
        logger.info(f"Epoch {itn+1}/10 - Loss: {losses.get('ner', 0):.2f}")
    
    # 5. AUTOMATIC DEPLOYMENT
    # The model is saved directly into the production-mapped folder.
    if not os.path.exists(MODEL_OUTPUT_DIR):
        os.makedirs(MODEL_OUTPUT_DIR, exist_ok=True)
    
    # Save the model directly into the folder where parse_engine.py loads from
    nlp.to_disk(MODEL_OUTPUT_DIR)
    
    logger.info(f"Success! Training complete.")
    logger.info(f"Model weights automatically deployed to: {MODEL_OUTPUT_DIR}")
    logger.info("The Ingestion Service will now use these updated weights for all future messages.")

if __name__ == "__main__":
    train_and_save_model()
