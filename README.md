# Pharmacy AI Assistant

[![CI](https://github.com/kiroviro/pharmacy-ai-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/kiroviro/pharmacy-ai-assistant/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-34%25-yellow.svg)](htmlcov/index.html)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

AI-powered pharmacy assistant for Bulgarian-language medical consultations. Recommends OTC products based on symptoms using MedGemma medical AI, multi-stage retrieval, and safety validation.

## Integrations

This chatbot integrates seamlessly with the ViaPharma ecosystem:

- **[viapharma.us](https://viapharma.us)** - Main pharmacy platform for product catalog and customer service
- **pharmacy-to-shopify** - Product synchronization pipeline that imports OTC products into the chatbot's recommendation database

The chatbot serves as an intelligent product recommendation layer, helping customers find the right OTC medications based on their symptoms while directing them to viapharma.us for purchase.

## Architecture

```
User (Bulgarian)
      │
      ▼
┌─────────────────┐     ┌─────────────────┐
│ Intent          │────▶│ Non-medical     │──▶ Polite rejection
│ Classifier      │     │ Query?          │
└────────┬────────┘     └─────────────────┘
         │ Medical
         ▼
┌─────────────────┐
│ Translate       │
│ BG → EN         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ MedGemma        │────▶│ Safety Layer    │──▶ Red flag? → "Call 112"
│ Medical AI      │     │ (Red flags)     │
└────────┬────────┘     └─────────────────┘
         │
         ▼
┌─────────────────┐
│ Product Search  │
│ (ChromaDB RAG)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Translate       │
│ EN → BG         │
└────────┬────────┘
         │
         ▼
   Response + Disclaimer
```

## Quick Start

### Prerequisites

- Python 3.10+
- Mac with Apple Silicon (M1/M2/M3)
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

Place your product CSV in `data/products.csv`, then:

```bash
python -c "from src.product_store import get_product_store; ps = get_product_store(); ps.reload_products()"
```

### 4. Start the Server

```bash
python api_server.py
```

The API will be available at `http://localhost:8000`.

### 5. Connect Open WebUI

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
| `GET /hints` | Bulgarian UI hints |
| `GET /v1/models` | List models (OpenAI-compatible) |
| `POST /v1/chat/completions` | Chat (OpenAI-compatible) |
| `GET /docs` | **Swagger UI** - Interactive API docs |
| `GET /redoc` | ReDoc - Alternative API docs |

## Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# Or build manually
docker build -t pharmacy-ai-assistant .
docker run -p 8000:8000 -v ./output:/app/output:ro pharmacy-ai-assistant
```

The API will be available at `http://localhost:8000/docs` (Swagger UI).

## Configuration

Set environment variables with `VIAPHARMA_` prefix:

```bash
export VIAPHARMA_API_PORT=8000
export VIAPHARMA_LOG_LEVEL=INFO
export VIAPHARMA_PREWARM_MODELS=true
```

Or create a `.env` file (see `.env.example`).

## Testing

### Unit Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run with coverage (enforced minimum: 35%)
pytest tests/ --cov=src --cov-report=term-missing

# Generate HTML coverage report
pytest tests/ --cov=src --cov-report=html
# Open htmlcov/index.html in browser
```

**Current Coverage**: 39% (baseline established Feb 2026)

Coverage by component:
- ✅ Unified Processor: 92%
- ✅ Query Router: 91%
- ✅ Intent Classifier: 92%
- ✅ Safety Layer: 77%
- ⚠️ Medical Model: 59%
- 🔴 Orchestrator: 9% (god object - scheduled for refactor)
- 🔴 Product Store: 18%

**Goal**: Increase to 60% by Q2 2026, 80% by Q3 2026

### End-to-End (E2E) Quality Tests

Comprehensive quality validation with 352 real Bulgarian medical queries:

```bash
# Run E2E tests with full quality checks
python e2e_query_tests.py

# Results saved to: output/test_results.json, test_results.txt
```

**Test Coverage**:
- 352 real-world Bulgarian medical queries
- Symptom queries (headache, fever, cough, etc.)
- Medication queries (product names, comparisons)
- Safety validation (emergency detection)
- Template compliance checks
- Language quality validation

**Quality Metrics Tracked**:
- Garbage text detection (target: <1%)
- Template compliance (target: >95% with ingredients)
- Language quality (target: >95% Bulgarian)
- Response time (target: <10s p99)
- Product relevance (target: >99%)

**Last E2E Run**: February 14, 2026
- 322/352 queries passed core functionality (91.5%)
- 6 CRITICAL garbage text issues
- 231 template compliance warnings

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design.

## Safety Features

- Emergency symptom detection (redirects to 112)
- Urgent symptom warnings (advises doctor visit)
- OTC-only product filtering
- Bulgarian language support throughout

## License

MIT License - See [LICENSE](LICENSE) for details.
