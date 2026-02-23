# Pharmacy AI Assistant

[![CI](https://github.com/kiroviro/pharmacy-ai-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/kiroviro/pharmacy-ai-assistant/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-68%25-green.svg)](htmlcov/index.html)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

AI-powered pharmacy assistant for Bulgarian-language medical consultations. Recommends OTC products based on symptoms using MedGemma medical AI, multi-stage retrieval, and safety validation.

## Integrations

This chatbot integrates seamlessly with the ViaPharma ecosystem:

- **[viapharma.us](https://viapharma.us)** — Main pharmacy platform for product catalog and customer service
- **pharmacy-to-shopify** — Product synchronization pipeline that imports OTC products into the chatbot's recommendation database
- **cloudly-v3** — Next.js frontend with chat panel UI that connects to this API

The chatbot serves as an intelligent product recommendation layer, helping customers find the right OTC medications based on their symptoms while directing them to viapharma.us for purchase.

## Architecture

Uses a **unified LLM-driven processor** — a single MedGemma call handles intent classification, safety screening, medical reasoning, and product matching:

```
User (Bulgarian)
      │
      ▼
┌─────────────────┐
│ Hard-coded       │──── Emergency? ────▶ "Обадете се на 112"
│ Safety Layer     │     (non-negotiable)
└────────┬────────┘
         │ Safe
         ▼
┌─────────────────┐
│ Unified          │     Single LLM call handles:
│ Processor        │     • Intent classification
│ (MedGemma 4B)    │     • Medical reasoning
│                  │     • Query translation (BG→EN)
│                  │     • Product extraction
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Two-Stage        │     1. ChromaDB vector search (top-10)
│ Product          │     2. LLM refinement (best 3)
│ Retrieval        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Response         │     • Validation & garbage filtering
│ Builder +        │     • EN→BG translation (MarianMT)
│ Translate        │     • Template formatting + disclaimers
└────────┬────────┘
         │
         ▼
   Response + Disclaimer
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed system design.

## Quick Start

### Prerequisites

- Python 3.11+
- Mac with Apple Silicon (M1/M2/M3/M4) — required for MLX inference
- ~8GB disk space for models

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Download MedGemma Model

```bash
# Login to Hugging Face (requires account)
huggingface-cli login

# Download model
huggingface-cli download mlx-community/medgemma-4b-it-bf16 --local-dir models/medgemma-4b-it-bf16
```

### 3. Load Product Catalogue

Product data lives in `data/products_processed.csv` (~9,600 products). To reload into ChromaDB:

```bash
python -c "from src.product_store import get_product_store; ps = get_product_store(); ps.reload_products()"
```

### 4. Start the Server

```bash
python api_server.py
```

The API will be available at `http://localhost:8000` (Swagger UI at `/docs`).

### 5. Connect a Frontend

**Option A: cloudly-v3 (recommended)**

The cloudly-v3 Next.js app has a built-in chat panel that connects to this API.

**Option B: Open WebUI**

```bash
docker run -d --name open-webui -p 3000:8080 \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY=dummy \
  ghcr.io/open-webui/open-webui:main
```

Open `http://localhost:3000` and select the `viapharma-assistant` model.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check with model status |
| `GET /health/live` | Kubernetes liveness probe |
| `GET /health/ready` | Kubernetes readiness probe |
| `GET /hints` | Bulgarian UI hints and welcome message |
| `GET /metrics` | Application metrics (request counts, latencies, cache stats) |
| `GET /v1/models` | List models (OpenAI-compatible) |
| `POST /v1/chat/completions` | Chat (OpenAI-compatible) |
| `GET /docs` | **Swagger UI** — Interactive API docs |
| `GET /redoc` | ReDoc — Alternative API docs |

## Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build manually
docker build -t pharmacy-ai-assistant .
docker run -p 8000:8000 -v ./output:/app/output:ro pharmacy-ai-assistant
```

> **Note:** MLX inference requires Apple Silicon. Docker images must target `linux/arm64` on Apple Silicon hosts.

## Configuration

All settings managed via `src/config.py` (pydantic-settings). Set environment variables with `VIAPHARMA_` prefix:

```bash
export VIAPHARMA_API_PORT=8000
export VIAPHARMA_LOG_LEVEL=INFO
export VIAPHARMA_PREWARM_MODELS=true
export VIAPHARMA_MEDGEMMA_MODEL_PATH=./models/medgemma-4b-it-bf16
```

Or create a `.env` file (see `.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `VIAPHARMA_API_PORT` | 8000 | API server port |
| `VIAPHARMA_LOG_LEVEL` | INFO | Logging level |
| `VIAPHARMA_LOG_JSON` | true | JSON structured logging |
| `VIAPHARMA_MAX_MESSAGE_LENGTH` | 2000 | Max user message length |
| `VIAPHARMA_RATE_LIMIT_PER_MINUTE` | 30 | Rate limit per IP |
| `VIAPHARMA_ENABLE_RATE_LIMITING` | true | Enable rate limiting |
| `VIAPHARMA_PREWARM_MODELS` | true | Pre-load models on startup |
| `VIAPHARMA_MEDGEMMA_MODEL_PATH` | `./models/medgemma-4b-it-bf16` | Path to MedGemma model |

## Testing

### Unit Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run with coverage (enforced minimum: 35%)
pytest tests/ --cov=src --cov-report=term-missing

# Generate HTML coverage report
pytest tests/ --cov=src --cov-report=html
```

**Current Coverage**: 68% (target: 80%)

### End-to-End (E2E) Quality Tests

Comprehensive quality validation organized by category in `tests/e2e/`:

```bash
# Run all E2E tests
pytest tests/e2e/ -v

# Run by category
pytest tests/e2e/test_symptom_queries.py -v
pytest tests/e2e/test_medication_queries.py -v
pytest tests/e2e/test_safety_queries.py -v
pytest tests/e2e/test_catalog_queries.py -v
pytest tests/e2e/test_edge_cases.py -v
```

**Quality Metrics Tracked**:
- Garbage text detection (target: <1%)
- Template compliance (target: >95% with ingredients)
- Language quality (target: >95% Bulgarian)
- Response time (target: <10s p99)
- Product relevance (target: >99%)

## Project Structure

```
pharmacy-ai-assistant/
├── api_server.py                        # OpenAI-compatible FastAPI server
├── src/
│   ├── config.py                        # Centralized settings (pydantic-settings)
│   ├── logging_config.py                # Structured JSON logging
│   ├── unified_processor.py             # LLM-driven processor (intent + reasoning)
│   ├── medical_model.py                 # MedGemma MLX wrapper
│   ├── translator.py                    # EN→BG translation (MarianMT)
│   ├── safety.py                        # Hard-coded emergency detection
│   ├── product_store.py                 # ChromaDB vector search
│   ├── data_loader.py                   # CSV → ChromaDB loader
│   ├── pipeline/
│   │   ├── orchestrator.py              # Main pipeline (~1,210 LOC)
│   │   ├── product_matcher.py           # Product search & ranking
│   │   ├── safety_validator.py          # Age/severity filtering
│   │   ├── ingredient_analyzer.py       # Ingredient extraction & display
│   │   ├── response_builder.py          # Response formatting
│   │   ├── response_validator.py        # Garbage text filtering
│   │   ├── query_router.py              # Query routing logic
│   │   ├── product_ingredients.py       # Ingredient parsing
│   │   ├── conditions.py                # User condition extraction
│   │   └── models.py                    # Data models (Product, PipelineResult)
│   ├── services/
│   │   ├── medical_reasoning_service.py # Medical reasoning service
│   │   ├── product_recommendation_service.py
│   │   └── safety_check_service.py      # Safety check service
│   ├── common/
│   │   ├── models.py                    # Shared data models
│   │   └── contraindications.py         # Drug contraindications
│   └── prompts/
│       └── unified_prompt.py            # LLM prompt templates
├── tests/
│   ├── e2e/                             # E2E quality tests (5 files)
│   ├── contracts/                       # Test contracts & builders
│   └── test_*.py                        # Unit & integration tests (~30 files)
├── data/
│   ├── products_processed.csv           # Product catalogue (~9,600 products)
│   └── chromadb/                        # Vector database
├── models/                              # MedGemma model (git-ignored)
├── .github/workflows/
│   ├── ci.yml                           # Tests, linting, security scanning
│   └── price-sync.yml                   # Daily price sync from benu.bg
└── docs/                                # Architecture, tech debt, analysis
```

## Safety Features

- **Emergency detection** — hard-coded keyword matching redirects to 112 (non-negotiable, never removed)
- **Urgent symptom warnings** — advises doctor visit within 24-48h
- **OTC-only filtering** — prescription drugs never shown
- **Response validation** — garbage text filtering catches LLM hallucinations
- **Bulgarian language support** throughout the pipeline

## Performance

- **MLX single-threaded** — `max_workers=1` is correct; concurrent MLX inference causes segfault
- **Single request latency**: ~2.7s per query
- **Maximum throughput**: ~22 req/min (single instance)
- **Rate limiting**: 30 req/min per IP (in-memory, process-local)

## License

MIT License — See [LICENSE](LICENSE) for details.
