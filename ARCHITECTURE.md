# ViaPharma OTC Chatbot with MedGemma

## Overview

Build a Bulgarian-language medical chatbot for viapharma.us that understands symptoms and recommends OTC products from a catalogue of ~10-11k items. Runs locally on Mac M-series with option to scale later.

## Architecture

Uses **Perplexity-style two-stage retrieval** for accurate product matching:
1. **Stage 1**: Vector DB returns top-K candidates (fast, cheap)
2. **Stage 2**: LLM refines and picks best matches (accurate)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE                                      │
└──────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────┐
  │   Open WebUI    │
  │   Port 3000     │
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  api_server.py  │
  │   Port 8000     │
  │  (OpenAI API)   │
  └────────┬────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              PIPELINE FLOW                                    │
└──────────────────────────────────────────────────────────────────────────────┘

  User Input (Bulgarian)
        │
        ▼
┌───────────────┐
│ 1. INTENT     │──── Not medical? ────▶ Polite rejection
│   CLASSIFIER  │                        "Мога да помогна само с
│  (Keywords)   │                         здравни въпроси"
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

## User Interface

### Open WebUI
- Full-featured chat interface
- Conversation history
- Model selection
- Runs via `api_server.py` (OpenAI-compatible API)
- See `OPEN_WEBUI_SETUP.md` for setup instructions

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

### Step 1: Intent Classifier (`src/intent_classifier.py`)
- **Method**: Keyword-based classification (fast, no ML model needed)
- **Purpose**: Filter non-medical queries (weather, jokes, cooking, etc.)
- **Languages**: Bulgarian and English medical terms supported
- **Keywords**:
  - Medical: symptoms, body parts, medications, treatment actions
  - Non-medical: weather, news, sports, recipes, travel, banking
- **Output**: `(is_medical: bool, confidence: float, reason: str)`
- **Behavior**: Permissive - defaults to medical if unclear (better to process than reject)
- **Status**: ✅ Implemented

### Step 2: Translation BG → EN (`src/translator.py`)
- **Model**: `Helsinki-NLP/opus-mt-bg-en` (MarianMT)
- **Purpose**: Translate Bulgarian symptoms to English for MedGemma
- **Cache**: LRU cache for repeated translations
- **Status**: ✅ Implemented

### Step 3: Medical Reasoning (`src/medical_model.py`)
- **Model**: `mlx-community/medgemma-4b-it-bf16`
- **Purpose**: Understand symptoms, suggest treatment categories
- **Prompt**: Structured to output treatment types, not specific products
- **Status**: ✅ Implemented

### Step 4: Safety Layer (`src/safety.py`)
- **Purpose**: Detect dangerous symptoms and ensure safe recommendations
- **Severity Levels**:
  - **Emergency** 🚨: Immediate 112 call (chest pain, difficulty breathing, seizures, poisoning, suicidal thoughts)
  - **Urgent** ⚠️: See doctor within 24-48h (blood in urine/stool, high fever >3 days, severe headache, jaundice)
  - **Warning** ℹ️: Monitor and seek help if worsens (persistent cough, unexplained weight loss, changing moles)
- **Languages**: Bulgarian and English symptom detection
- **OTC Filter**: Removes non-OTC products from recommendations
- **Output**: `SafetyCheckResult` with severity, matched symptoms, and localized message
- **Status**: ✅ Implemented

### Step 5a: Product Retrieval (`src/product_store.py`)
- **Database**: ChromaDB with ~10-11k products
- **Embeddings**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **Method**: Vector similarity search
- **Returns**: Top 10 candidate products (fast, cheap)
- **Status**: ✅ Implemented

### Step 5b: Product Refinement (`src/medical_model.py`)
- **Model**: MedGemma (reuses loaded model)
- **Input**: Original query + top-K candidates from vector search
- **Method**: LLM picks best matches considering medical context
- **Returns**: Top 3 most relevant products
- **Status**: ✅ Implemented

### Step 6: Translation EN → BG (`src/translator.py`)
- **Model**: `Helsinki-NLP/opus-mt-en-bg` (MarianMT)
- **Purpose**: Translate response back to Bulgarian
- **Status**: ✅ Implemented

### Step 7: Response Formatting (`src/pipeline.py`)
- Product recommendations with prices (BGN and EUR)
- Safety disclaimers added based on symptom severity
- Standard disclaimer always shown
- **Status**: ✅ Implemented

## Project Structure

```
medgemma/
├── .env                        # HF token (git-ignored)
├── .env.example                # Template for .env
├── .gitignore
├── ARCHITECTURE.md             # This file
├── OPEN_WEBUI_SETUP.md         # Open WebUI setup guide
├── requirements.txt            # Python dependencies
│
├── api_server.py               # OpenAI-compatible API (for Open WebUI)
│
├── models/
│   └── medgemma-4b-it-bf16/    # MedGemma model (git-ignored)
│
├── data/
│   ├── .gitkeep
│   ├── products.csv            # Product catalogue (git-ignored)
│   └── chromadb/               # Vector database (git-ignored)
│
├── src/
│   ├── __init__.py
│   ├── intent_classifier.py    # Step 1: Medical query detection
│   ├── translator.py           # Step 2 & 6: BG↔EN translation
│   ├── medical_model.py        # Step 3 & 5b: MedGemma wrapper
│   ├── safety.py               # Step 4: Red-flag detection + OTC filter
│   ├── product_store.py        # Step 5a: ChromaDB vector search
│   ├── data_loader.py          # CSV to ChromaDB loader
│   └── pipeline.py             # Main pipeline orchestrator
│
├── output/                     # Generated files (git-ignored)
│
└── tests/
    └── .gitkeep
```

## Dependencies

```
# Core ML
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
pydantic                # Request/response models

# Utils
pandas                  # CSV handling
python-dotenv           # Environment variables
```

## Running the Application

```bash
# Terminal 1: Start API server
python api_server.py

# Terminal 2: Start Open WebUI (Docker)
docker run -d --name open-webui -p 3000:8080 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=dummy \
  ghcr.io/open-webui/open-webui:main

# Open http://localhost:3000
```

## Safety Measures

### Emergency Symptoms 🚨 (Call 112 immediately)
Blocks all recommendations and shows emergency message:
- Chest pain, pressure, or tightness
- Difficulty breathing, choking
- Loss of consciousness, fainting
- Paralysis, facial drooping, slurred speech
- Sudden vision loss
- Seizures, convulsions
- Severe bleeding
- Anaphylaxis
- Poisoning, overdose
- Suicidal thoughts

### Urgent Symptoms ⚠️ (See doctor within 24-48h)
Blocks recommendations and advises medical consultation:
- Blood in urine or stool
- Vomiting blood
- Severe abdominal pain
- High fever (>39°C) for 3+ days
- Worst headache ever, thunderclap headache
- Stiff neck with fever
- Facial swelling, swollen tongue/lips
- Jaundice (yellow eyes/skin)
- Confusion, disorientation
- Severe back/kidney pain
- Unable to urinate

### Warning Symptoms ℹ️ (Monitor, add disclaimer)
Allows recommendations but adds warning message:
- Persistent cough (>2 weeks)
- Unexplained weight loss
- Night sweats
- Persistent fatigue (>2 weeks)
- Lumps, nodules, growths
- Changing moles
- Non-healing wounds
- Difficulty swallowing
- Frequent headaches
- Vision/hearing changes

### OTC-Only Enforcement
- Product catalogue has `is_otc: bool` column
- Safety layer filters to only OTC products
- Prescription drugs never shown

### Disclaimers (always shown)
- "Това е информационна услуга, не медицински съвет"
- "Консултирайте се с фармацевт за повече информация"

## Implementation Status

| Component | Status | File |
|-----------|--------|------|
| OpenAI API | ✅ Done | `api_server.py` |
| Pipeline | ✅ Done | `src/pipeline.py` |
| MedGemma | ✅ Done | `src/medical_model.py` |
| Translation | ✅ Done | `src/translator.py` |
| Product Store | ✅ Done | `src/product_store.py` |
| Data Loader | ✅ Done | `src/data_loader.py` |
| Intent Classifier | ✅ Done | `src/intent_classifier.py` |
| Safety Layer | ✅ Done | `src/safety.py` |

## Next Steps

1. **Product Catalogue** - Load your CSV into ChromaDB
2. **Testing** - Unit and integration tests
3. **Performance Optimization** - Caching for common queries
