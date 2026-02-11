# ViaPharma OTC Chatbot with MedGemma

## Overview
Build a Bulgarian-language medical chatbot for viapharma.us that understands symptoms and recommends OTC products from a catalogue of ~10-11k items. Runs locally on Mac M-series with option to scale later.

## Architecture

Uses **Perplexity-style two-stage retrieval** for accurate product matching:
1. **Stage 1**: Vector DB returns top-K candidates (fast, cheap)
2. **Stage 2**: LLM refines and picks best matches (accurate)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              PIPELINE FLOW                                    │
└──────────────────────────────────────────────────────────────────────────────┘

  User Input (Bulgarian)
        │
        ▼
┌───────────────┐
│ 1. INTENT     │──── Not medical? ────▶ Polite rejection
│   CLASSIFIER  │                        "Мога да помогна само с
│  (DistilBERT) │                         здравни въпроси"
└───────┬───────┘
        │ Medical query
        ▼
┌───────────────┐
│ 2. TRANSLATE  │
│   BG → EN     │
│  (MarianMT)   │
└───────┬───────┘
        │
        ▼
┌───────────────┐     ┌───────────────┐
│ 3. MEDGEMMA   │────▶│ 4. SAFETY     │──── Red flag? ────▶ "Моля, консултирайте
│   Medical     │     │    LAYER      │                      се с лекар"
│   Reasoning   │     │  (Python)     │
└───────────────┘     └───────┬───────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        │         TWO-STAGE RETRIEVAL               │
        │         (Perplexity Pattern)              │
        └─────────────────────┬─────────────────────┘
                              │
                              ▼
                      ┌───────────────┐
                      │ 5a. VECTOR DB │
                      │   RETRIEVAL   │◄─── FAST: Get top-K candidates
                      │  (ChromaDB)   │     from ~10k products
                      └───────┬───────┘
                              │ top-K candidates
                              ▼
                      ┌───────────────┐
                      │ 5b. LLM       │◄─── ACCURATE: Pick best matches
                      │   REFINEMENT  │     given query + candidates
                      │  (MedGemma)   │
                      └───────┬───────┘
                              │ best matches
                              ▼
                      ┌───────────────┐
                      │ 6. TRANSLATE  │
                      │   EN → BG     │
                      │  (MarianMT)   │
                      └───────┬───────┘
                              │
                              ▼
                      ┌───────────────┐
                      │ 7. RESPONSE   │
                      │   + Disclaimer│
                      │   to UI       │
                      └───────────────┘
```

## Two-Stage Retrieval (Key Innovation)

Inspired by Perplexity's finance widget architecture:

### Stage 1: Vector DB Retrieval (FAST)
- **Input**: Medical reasoning from MedGemma
- **Process**: Nearest-neighbor search over product embeddings
- **Output**: Top 10 candidate products
- **Speed**: ~10-50ms

### Stage 2: LLM Refinement (ACCURATE)
- **Input**: Original query + candidate products
- **Process**: LLM evaluates each candidate for relevance
- **Output**: Best 3 products ranked by match quality
- **Benefits**:
  - Considers contraindications mentioned by user
  - Weighs symptom-product match accuracy
  - Can filter based on user context (allergies, age, etc.)

## Pipeline Components

### Step 1: Intent Classifier
- **Model**: `distilbert-base-multilingual-cased` or Bulgarian-specific model
- **Purpose**: Filter non-medical queries (weather, jokes, etc.)
- **Output**: `is_medical: bool`
- **File**: `src/intent_classifier.py`

### Step 2: Translation BG → EN
- **Model**: `Helsinki-NLP/opus-mt-bg-en` (MarianMT)
- **Purpose**: Translate Bulgarian symptoms to English for MedGemma
- **Cache**: Common phrases cached for speed
- **File**: `src/translator.py`

### Step 3: Medical Reasoning (MedGemma)
- **Model**: `mlx-community/medgemma-4b-it-bf16` (already downloaded)
- **Purpose**: Understand symptoms, suggest treatment categories
- **Prompt**: Structured to output treatment types, not specific products
- **File**: `src/medical_model.py`

### Step 4: Safety Layer
- **Red-flag symptoms**: chest pain, difficulty breathing, sudden vision loss, etc.
- **OTC whitelist**: Only recommend products marked as OTC in catalogue
- **Prescription filter**: Block any prescription drug recommendations
- **File**: `src/safety.py`

### Step 5a: Product Retrieval (Vector DB)
- **Database**: ChromaDB with ~10-11k products
- **Embeddings**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **Method**: Vector similarity search
- **Returns**: Top 10 candidate products (fast, cheap)
- **File**: `src/product_mapper.py`

### Step 5b: Product Refinement (LLM)
- **Model**: MedGemma (or smaller/cheaper model)
- **Input**: Original query + top-K candidates from vector search
- **Method**: LLM picks best matches considering medical context
- **Returns**: Top 3 most relevant products
- **File**: `src/product_refiner.py`

### Step 6: Translation EN → BG
- **Model**: `Helsinki-NLP/opus-mt-en-bg` (MarianMT)
- **Purpose**: Translate response back to Bulgarian
- **File**: `src/translator.py` (same file, both directions)

### Step 7: Response Formatting
- Product recommendations with prices
- Always include disclaimer
- "Add to cart" / "View product" links
- **File**: `src/response_formatter.py`

## Project Structure

```
medgemma/
├── .env                        # HF token (exists)
├── .gitignore                  # (exists)
├── models/
│   └── medgemma-4b-it-bf16/    # MedGemma (exists)
├── data/
│   ├── products.csv            # Product catalogue (~10-11k items)
│   └── red_flags.json          # Red-flag symptoms list
├── src/
│   ├── __init__.py
│   ├── intent_classifier.py    # Step 1: Filter non-medical
│   ├── translator.py           # Step 2 & 6: BG↔EN translation
│   ├── medical_model.py        # Step 3: MedGemma wrapper
│   ├── safety.py               # Step 4: Red flags + OTC filter
│   ├── product_mapper.py       # Step 5a: Vector DB retrieval
│   ├── product_refiner.py      # Step 5b: LLM refinement (NEW)
│   ├── response_formatter.py   # Step 7: Format output
│   └── pipeline.py             # Orchestrates all steps
├── app.py                      # FastAPI + Gradio UI
├── requirements.txt
└── tests/
    ├── test_intent.py
    ├── test_translation.py
    ├── test_safety.py
    └── test_pipeline.py
```

## Dependencies

```
# Core
mlx-lm                  # MedGemma inference on Mac
transformers            # Intent classifier + MarianMT
torch                   # PyTorch backend
sentencepiece           # Tokenizer for MarianMT

# RAG
chromadb                # Vector database
sentence-transformers   # Multilingual embeddings

# API & UI
fastapi                 # REST API
uvicorn                 # ASGI server
gradio                  # Quick prototype UI

# Utils
pandas                  # CSV handling
python-dotenv           # Environment variables
```

## Safety Measures

### Red-Flag Symptoms (escalate to doctor)
- Chest pain or pressure
- Difficulty breathing
- Sudden severe headache
- Vision changes
- Numbness/weakness on one side
- Persistent high fever (>39°C for 3+ days)
- Blood in stool/urine
- Severe abdominal pain

### OTC-Only Enforcement
- Product catalogue has `is_otc: bool` column
- Safety layer filters to only OTC products
- Prescription drugs never shown

### Disclaimers (always shown)
- "Това е информационна услуга, не медицински съвет"
- "Консултирайте се с фармацевт за повече информация"

## Sample Interaction

```
User: Имам силно главоболие и температура от два дни

Pipeline:
1. Intent: ✅ Medical query
2. Translate: "I have a severe headache and fever for two days"
3. MedGemma: "Suggests antipyretics and analgesics for headache with fever"
4. Safety: ✅ No red flags (fever < 3 days)
5a. Vector DB: Returns 10 candidates (pain relievers, fever reducers)
5b. LLM Refine: Picks best 3 based on symptom match
6. Translate back to Bulgarian

Bot: Въз основа на вашите симптоми, ето някои опции:

1. **Парацетамол 500mg** (5.99 лв)
   - Облекчава главоболие и понижава температурата
   - Дозировка: 1-2 таблетки на всеки 4-6 часа

2. **Ибупрофен 400mg** (7.99 лв)
   - Противовъзпалително + обезболяващо
   - Да се приема с храна

⚠️ Ако температурата продължи повече от 3 дни, моля консултирайте се с лекар.

ℹ️ Това е информационна услуга. За повече информация се консултирайте с фармацевт.
```

## Implementation Order

1. **Phase 1: Core Infrastructure** ✅ In Progress
   - [x] Project structure
   - [x] Gradio UI (placeholder)
   - [x] Pipeline skeleton with two-stage retrieval
   - [ ] Product catalogue loader + ChromaDB setup
   - [ ] Translation module (MarianMT both directions)
   - [ ] Basic MedGemma wrapper

2. **Phase 2: Safety & Intelligence**
   - [ ] Intent classifier
   - [ ] Safety layer with red-flag detection
   - [ ] Product refinement with LLM (Step 5b)

3. **Phase 3: Integration**
   - [ ] Full pipeline orchestration
   - [ ] FastAPI endpoints
   - [ ] Gradio UI polish

4. **Phase 4: Testing & Polish**
   - [ ] Unit tests for each component
   - [ ] End-to-end integration tests
   - [ ] Performance optimization (caching)

## Future Enhancements (Out of Scope for Now)
- User authentication
- Conversation history
- Product stock availability
- Shopping cart integration
- Analytics dashboard
