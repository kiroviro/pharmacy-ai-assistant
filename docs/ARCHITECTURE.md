# Pharmacy AI Assistant

## Overview

AI-powered pharmacy assistant for viapharma.us that understands Bulgarian-language symptom descriptions and recommends OTC products from a catalogue of ~9,600 items. Built with MedGemma 4B medical AI via MLX, runs locally on Mac Apple Silicon.

## Ecosystem Integration

This AI assistant is part of the ViaPharma pharmacy technology stack:

- **Product Data Source**: Receives product catalog updates from the **pharmacy-to-shopify** synchronization pipeline
- **Customer Touchpoint**: Integrated with **[viapharma.us](https://viapharma.us)** to provide intelligent product recommendations
- **Frontend**: **cloudly-v3** Next.js app with chat panel connects to this API
- **Data Flow**: `pharmacy-to-shopify` → Product CSV → ChromaDB embeddings → MedGemma recommendations → Customer interface

## Architecture

### Unified Processor (Active Architecture)

The current architecture uses a **single LLM call** (unified processor) that handles intent classification, safety screening, medical reasoning, and product matching in one pass. This replaced the previous multi-step pipeline (separate intent classifier, BG→EN translation, etc.) which was removed in Week 3.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE                                     │
└──────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────┐     ┌─────────────────┐
  │  cloudly-v3     │     │   Open WebUI    │
  │  Port 3007      │     │   Port 3000     │
  └────────┬────────┘     └────────┬────────┘
           │                       │
           └───────────┬───────────┘
                       ▼
  ┌─────────────────────────────────┐
  │         api_server.py           │
  │         Port 8000               │
  │    (OpenAI-compatible API)      │
  │    max_workers=1 (MLX limit)    │
  └────────────┬────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              PIPELINE FLOW                                   │
└──────────────────────────────────────────────────────────────────────────────┘

  User Input (Bulgarian)
        │
        ▼
┌───────────────┐
│ 1. HARD-CODED │──── Emergency? ────▶ "Обадете се на 112"
│    SAFETY     │     (keyword-based,
│   (safety.py) │      non-negotiable)
└───────┬───────┘
        │ Safe
        ▼
┌───────────────┐
│ 2. UNIFIED    │     Single LLM call handles:
│   PROCESSOR   │     • Intent classification (medical vs non-medical)
│  (MedGemma    │     • Query translation (BG → EN, internally)
│    4B, MLX)   │     • Medical reasoning
│               │     • Product extraction criteria
└───────┬───────┘
        │
        ▼
┌─────────────────────────────────────────┐
│       TWO-STAGE RETRIEVAL               │
│       (Perplexity Pattern)              │
└─────────────────────┬───────────────────┘
                      │
                      ▼
              ┌───────────────┐
              │ 3a. VECTOR DB │
              │   RETRIEVAL   │◄─── FAST: Get top-10 candidates
              │  (ChromaDB)   │     from ~9,600 products
              └───────┬───────┘
                      │ top-10 candidates
                      ▼
              ┌───────────────┐
              │ 3b. LLM       │◄─── ACCURATE: Pick best 3 matches
              │   REFINEMENT  │     given query + candidates
              │  (MedGemma)   │
              └───────┬───────┘
                      │ best matches
                      ▼
              ┌───────────────┐
              │ 4. RESPONSE   │     • Garbage text filtering
              │   VALIDATION  │     • Template compliance
              │   + BUILDER   │     • Language quality checks
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ 5. TRANSLATE  │
              │   EN → BG     │
              │  (MarianMT)   │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ 6. RESPONSE   │
              │   + Disclaimer│
              │   to UI       │
              └───────────────┘
```

## Two-Stage Retrieval (Key Innovation)

Inspired by Perplexity's finance widget architecture:

### Stage 1: Vector DB Retrieval (FAST)
- **Input**: Medical reasoning from unified processor
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

### Step 1: Hard-Coded Safety Layer (`src/safety.py`)
- **Method**: Keyword-based matching (Bulgarian + English)
- **Purpose**: Detect emergency/urgent symptoms before any LLM processing
- **Non-negotiable**: This layer is never removed — medical safety requires redundancy
- **Output**: `SafetyCheckResult` with severity, matched symptoms, and localized message

### Step 2: Unified Processor (`src/unified_processor.py`)
- **Model**: `mlx-community/medgemma-4b-it-bf16` via MLX
- **Purpose**: Single LLM call handles intent, translation, reasoning, extraction
- **Replaces**: Legacy intent classifier, BG→EN translator, separate reasoning step
- **Coverage**: 92% test coverage

### Step 3a: Product Retrieval (`src/product_store.py`)
- **Database**: ChromaDB with ~9,600 products
- **Embeddings**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- **Method**: Vector similarity search
- **Returns**: Top 10 candidate products

### Step 3b: Product Refinement (`src/pipeline/product_matcher.py`)
- **Model**: MedGemma (reuses loaded model)
- **Input**: Original query + top-10 candidates from vector search
- **Method**: LLM picks best matches considering medical context
- **Returns**: Top 3 most relevant products

### Step 4: Response Validation (`src/pipeline/response_validator.py`)
- **Purpose**: Catch LLM hallucinations and garbage text
- **Method**: 325+ garbage patterns, template compliance checks
- **Consolidation**: TextValidator class handles all validation

### Step 5: Translation EN → BG (`src/translator.py`)
- **Model**: `Helsinki-NLP/opus-mt-en-bg` (MarianMT)
- **Purpose**: Translate response back to Bulgarian
- **Note**: BG→EN query translation was removed — unified processor handles it

### Step 6: Response Formatting (`src/pipeline/response_builder.py`)
- Product recommendations with prices (BGN and EUR)
- Active ingredient display
- Safety disclaimers based on symptom severity
- Standard disclaimer always shown

## Project Structure

```
pharmacy-ai-assistant/
├── api_server.py                        # OpenAI-compatible FastAPI server
│
├── src/
│   ├── config.py                        # Centralized config (pydantic-settings)
│   ├── logging_config.py                # Structured JSON logging
│   ├── unified_processor.py             # Unified LLM processor (492 LOC)
│   ├── medical_model.py                 # MedGemma MLX wrapper
│   ├── translator.py                    # EN→BG translation (MarianMT)
│   ├── safety.py                        # Hard-coded safety layer
│   ├── product_store.py                 # ChromaDB vector search
│   ├── data_loader.py                   # CSV → ChromaDB loader
│   ├── safety_embeddings.py             # Safety embedding search
│   ├── medical_terms_validator.py       # Medical term validation
│   │
│   ├── pipeline/                        # Pipeline module (modular)
│   │   ├── orchestrator.py              # Main pipeline (~1,210 LOC)
│   │   ├── product_matcher.py           # Product search & ranking (148 LOC)
│   │   ├── safety_validator.py          # Age/severity filtering (72 LOC)
│   │   ├── ingredient_analyzer.py       # Ingredient extraction (215 LOC)
│   │   ├── response_builder.py          # Response formatting (227 LOC)
│   │   ├── response_validator.py        # Garbage filtering (745 LOC)
│   │   ├── query_router.py              # Query routing logic
│   │   ├── product_ingredients.py       # Ingredient parsing
│   │   ├── conditions.py                # User condition extraction
│   │   ├── models.py                    # Data models (Product, PipelineResult)
│   │   ├── constants.py                 # Keywords, symptom mappings
│   │   └── symptom_mappings.py          # Symptom→product mappings
│   │
│   ├── services/                        # Service layer
│   │   ├── medical_reasoning_service.py # Medical reasoning (97 LOC)
│   │   ├── product_recommendation_service.py # Product matching (86 LOC)
│   │   └── safety_check_service.py      # Safety checks (70 LOC)
│   │
│   ├── common/
│   │   ├── models.py                    # Shared data models
│   │   └── contraindications.py         # Drug contraindications
│   │
│   └── prompts/
│       └── unified_prompt.py            # LLM prompt templates
│
├── tests/
│   ├── conftest.py                      # Pytest fixtures
│   ├── test_safety.py                   # Safety tests (70 tests)
│   ├── test_unified_processor.py        # Unified processor tests
│   ├── test_ingredient_analyzer.py      # Ingredient tests (34 tests)
│   ├── test_api.py                      # API integration tests
│   ├── test_*.py                        # ~30 test files total
│   ├── e2e/                             # E2E quality tests
│   │   ├── test_symptom_queries.py
│   │   ├── test_medication_queries.py
│   │   ├── test_safety_queries.py
│   │   ├── test_catalog_queries.py
│   │   └── test_edge_cases.py
│   └── contracts/                       # Test contracts & builders
│
├── data/
│   ├── products_processed.csv           # Product catalogue (~9,600 products)
│   └── chromadb/                        # Vector database
│
├── models/
│   └── medgemma-4b-it-bf16/             # MedGemma model (git-ignored)
│
├── .github/workflows/
│   ├── ci.yml                           # Tests, ruff linting, bandit, pip-audit
│   └── price-sync.yml                   # Daily price sync from benu.bg
│
├── docs/
│   ├── ARCHITECTURE.md                  # This file
│   ├── TECHNICAL_DEBT.md                # Issue tracking
│   └── PERFORMANCE_ANALYSIS.md          # Performance data
│
├── output/                              # Generated files (git-ignored)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── requirements.txt
```

## API Endpoints

The API server (`api_server.py`) provides OpenAI-compatible endpoints plus custom health/hints endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Detailed health check (models loaded, products count, uptime) |
| `/health/live` | GET | Kubernetes liveness probe |
| `/health/ready` | GET | Kubernetes readiness probe |
| `/hints` | GET | Bulgarian UI hints and welcome message |
| `/metrics` | GET | Application metrics (request counts, latencies, cache stats) |
| `/v1/models` | GET | List available models (OpenAI-compatible) |
| `/v1/chat/completions` | POST | Chat endpoint (OpenAI-compatible) |
| `/docs` | GET | Swagger UI |
| `/redoc` | GET | ReDoc API docs |

## Configuration

All settings are managed via `src/config.py` using pydantic-settings. Environment variables use the `VIAPHARMA_` prefix:

| Setting | Default | Description |
|---------|---------|-------------|
| `VIAPHARMA_API_PORT` | 8000 | API server port |
| `VIAPHARMA_LOG_LEVEL` | INFO | Logging level |
| `VIAPHARMA_LOG_JSON` | true | Use JSON log format |
| `VIAPHARMA_MAX_MESSAGE_LENGTH` | 2000 | Max user message length |
| `VIAPHARMA_RATE_LIMIT_PER_MINUTE` | 30 | Rate limit per IP |
| `VIAPHARMA_ENABLE_RATE_LIMITING` | true | Enable rate limiting |
| `VIAPHARMA_PREWARM_MODELS` | true | Pre-load models on startup |
| `VIAPHARMA_MEDGEMMA_MODEL_PATH` | `./models/medgemma-4b-it-bf16` | Path to MedGemma model |

## Performance Characteristics

- **MLX single-threaded**: `max_workers=1` is correct — concurrent MLX inference causes segfault (exit code 139, validated via load testing)
- **Single request latency**: ~2.7s per query
- **Maximum throughput**: ~22 req/min (1,333 req/hour)
- **Rate limiting**: 30 req/min per IP (in-memory, process-local)

### Scaling Options (if needed)
1. **Horizontal scaling** (recommended): Deploy multiple pods (3 pods = 3x throughput)
2. **Model optimization**: Quantize to 2-bit or use smaller model variant
3. **Batching**: Process multiple queries in single inference call

## Dependencies

```
# Core ML
mlx-lm                  # MedGemma inference on Apple Silicon
transformers            # MarianMT translation
torch                   # PyTorch backend
sentencepiece           # Tokenizer for MarianMT

# RAG
chromadb                # Vector database
sentence-transformers   # Multilingual embeddings

# API
fastapi                 # REST API
uvicorn                 # ASGI server
pydantic                # Request/response models
pydantic-settings       # Configuration management

# Utils
pandas                  # CSV handling
python-dotenv           # Environment variables

# Testing
pytest                  # Test framework
pytest-cov              # Coverage reporting
pytest-asyncio          # Async test support

# Security
pip-audit               # Dependency vulnerability scanning
```

## Safety Measures

### Emergency Symptoms (Call 112 immediately)
Blocks all recommendations and shows emergency message:
- Chest pain, pressure, or tightness
- Difficulty breathing, choking
- Loss of consciousness, fainting
- Paralysis, facial drooping, slurred speech
- Seizures, convulsions
- Severe bleeding, anaphylaxis
- Poisoning, overdose
- Suicidal thoughts

### Urgent Symptoms (See doctor within 24-48h)
Blocks recommendations and advises medical consultation:
- Blood in urine or stool
- Severe abdominal pain
- High fever (>39C) for 3+ days
- Worst headache ever
- Stiff neck with fever
- Jaundice (yellow eyes/skin)
- Confusion, disorientation

### Warning Symptoms (Monitor, add disclaimer)
Allows recommendations but adds warning message:
- Persistent cough (>2 weeks)
- Unexplained weight loss
- Night sweats
- Persistent fatigue
- Changing moles
- Non-healing wounds

### OTC-Only Enforcement
- Product catalogue has `is_otc` column
- Safety layer filters to only OTC products
- Prescription drugs never shown

### Disclaimers (always shown)
- "Това е информационна услуга, не медицински съвет"
- "Консултирайте се с фармацевт за повече информация"

## Running the Application

```bash
# Terminal 1: Start API server
python api_server.py

# Terminal 2 (Option A): cloudly-v3 frontend
cd ../cloudly-v3 && npm run dev
# Open http://localhost:3007

# Terminal 2 (Option B): Open WebUI (Docker)
docker run -d --name open-webui -p 3000:8080 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=dummy \
  ghcr.io/open-webui/open-webui:main
# Open http://localhost:3000
```

## Running Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run E2E quality tests
pytest tests/e2e/ -v
```
