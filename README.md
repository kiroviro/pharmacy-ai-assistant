# ViaPharma OTC Chatbot

[![CI](https://github.com/YOUR_USERNAME/medgemma/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/medgemma/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Bulgarian-language medical chatbot that recommends OTC products based on symptoms. Powered by MedGemma on Mac M-series.

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

Open `http://localhost:3000` and select the `viapharma-medgemma` model.

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
docker build -t viapharma-medgemma .
docker run -p 8000:8000 -v ./output:/app/output:ro viapharma-medgemma
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

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design.

## Safety Features

- Emergency symptom detection (redirects to 112)
- Urgent symptom warnings (advises doctor visit)
- OTC-only product filtering
- Bulgarian language support throughout

## License

Proprietary - ViaPharma
