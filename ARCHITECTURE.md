# ViaPharma OTC Chatbot with MedGemma

## Overview

Build a Bulgarian-language medical chatbot for viapharma.us that understands symptoms and recommends OTC products from a catalogue of ~10-11k items. Runs locally on Mac M-series with option to scale later.

## Architecture

Uses **Perplexity-style two-stage retrieval** for accurate product matching:
1. **Stage 1**: Vector DB returns top-K candidates (fast, cheap)
2. **Stage 2**: LLM refines and picks best matches (accurate)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACES                                     │
└──────────────────────────────────────────────────────────────────────────────┘

  Option 1: Open WebUI                    Option 2: Gradio
  ┌─────────────────┐                    ┌─────────────────┐
  │   Open WebUI    │                    │  app_gradio.py  │
  │   Port 3000     │                    │   Port 7860     │
  └────────┬────────┘                    └────────┬────────┘
           │                                      │
           ▼                                      │
  ┌─────────────────┐                             │
  │  api_server.py  │                             │
  │   Port 8000     │                             │
  │  (OpenAI API)   │                             │
  └────────┬────────┘                             │
           │                                      │
           └──────────────┬───────────────────────┘
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

## User Interface Options

### Option 1: Open WebUI (Recommended)
- Full-featured chat interface
- Conversation history
- Model selection
- Runs via `api_server.py` (OpenAI-compatible API)
- See `OPEN_WEBUI_SETUP.md` for setup instructions

### Option 2: Gradio (Simple)
- Lightweight chat interface
- Quick testing and demos
- Runs via `app_gradio.py`
- Access at `http://localhost:7860`

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
- **Status**: Placeholder (always returns True)

### Step 2: Translation BG → EN
- **Model**: `Helsinki-NLP/opus-mt-bg-en` (MarianMT)
- **Purpose**: Translate Bulgarian symptoms to English for MedGemma
- **Cache**: Common phrases cached for speed
- **Status**: Placeholder (pass-through)

### Step 3: Medical Reasoning (MedGemma)
- **Model**: `mlx-community/medgemma-4b-it-bf16`
- **Purpose**: Understand symptoms, suggest treatment categories
- **Prompt**: Structured to output treatment types, not specific products
- **Status**: ✅ Implemented

### Step 4: Safety Layer
- **Red-flag symptoms**: chest pain, difficulty breathing, sudden vision loss, etc.
- **OTC whitelist**: Only recommend products marked as OTC in catalogue
- **Prescription filter**: Block any prescription drug recommendations
- **Status**: Placeholder (no filtering)

### Step 5a: Product Retrieval (Vector DB)
- **Database**: ChromaDB with ~10-11k products
- **Embeddings**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **Method**: Vector similarity search
- **Returns**: Top 10 candidate products (fast, cheap)
- **Status**: Placeholder (returns mock products)

### Step 5b: Product Refinement (LLM)
- **Model**: MedGemma (reuses loaded model)
- **Input**: Original query + top-K candidates from vector search
- **Method**: LLM picks best matches considering medical context
- **Returns**: Top 3 most relevant products
- **Status**: ✅ Implemented

### Step 6: Translation EN → BG
- **Model**: `Helsinki-NLP/opus-mt-en-bg` (MarianMT)
- **Purpose**: Translate response back to Bulgarian
- **Status**: Placeholder (pass-through)

### Step 7: Response Formatting
- Product recommendations with prices
- Always include disclaimer
- "Add to cart" / "View product" links
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
├── app_gradio.py               # Gradio chat interface
│
├── models/
│   └── medgemma-4b-it-bf16/    # MedGemma model (git-ignored)
│
├── data/
│   ├── .gitkeep
│   └── products.csv            # Product catalogue (git-ignored)
│
├── src/
│   ├── __init__.py
│   ├── medical_model.py        # MedGemma wrapper
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
gradio                  # Web UI (fallback)
pydantic                # Request/response models

# Utils
pandas                  # CSV handling
python-dotenv           # Environment variables
```

## Running the Application

### Quick Start (Gradio)
```bash
python app_gradio.py
# Open http://localhost:7860
```

### With Open WebUI
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

## Implementation Status

| Component | Status | File |
|-----------|--------|------|
| Gradio UI | ✅ Done | `app_gradio.py` |
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
