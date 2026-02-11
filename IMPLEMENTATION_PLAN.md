# ViaPharma MedGemma - Implementation Plan

**Based on:** TECHNICAL_REVIEW.md
**Goal:** Production-ready system

---

## Phase 1: Critical Fixes (P0) - Week 1

### 1.1 Add Unit Tests for Safety Layer
**File:** `tests/test_safety.py`

**Why:** Safety layer is critical - must never miss emergency symptoms.

**Tasks:**
- [ ] Create test fixtures with sample symptoms (Bulgarian + English)
- [ ] Test emergency symptoms detection (100% coverage required)
  - Chest pain, difficulty breathing, seizures, suicidal thoughts
- [ ] Test urgent symptoms detection
  - Blood in urine/stool, high fever, severe headache
- [ ] Test warning symptoms detection
- [ ] Test false positive prevention (common phrases that shouldn't trigger)
- [ ] Test OTC filter functionality

**Acceptance Criteria:**
- All emergency symptoms detected with 100% accuracy
- No false positives on common medical queries
- Tests run in < 5 seconds

---

### 1.2 Add Logging Infrastructure
**Files:** `src/logging_config.py`, updates to all modules

**Why:** Can't debug production issues without logs.

**Tasks:**
- [ ] Create `src/logging_config.py` with structured logging
- [ ] Add log levels: DEBUG, INFO, WARNING, ERROR
- [ ] Log format: JSON for production, human-readable for dev
- [ ] Add logging to:
  - [ ] `pipeline.py` - request start/end, timing, product count
  - [ ] `medical_model.py` - inference time, parse failures
  - [ ] `safety.py` - red flag detections
  - [ ] `api_server.py` - request/response logging
- [ ] Add request ID for tracing
- [ ] Configure log rotation

**Implementation:**
```python
# src/logging_config.py
import logging
import sys
from datetime import datetime

def setup_logging(level: str = "INFO", json_format: bool = False):
    """Configure application logging."""
    logger = logging.getLogger("viapharma")
    logger.setLevel(getattr(logging, level))

    if json_format:
        # JSON format for production
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"module": "%(module)s", "message": "%(message)s"}'
        )
    else:
        # Human readable for development
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(module)s | %(message)s'
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
```

---

## Phase 2: Security & Stability (P1) - Week 2

### 2.1 Fix Async Blocking in API
**File:** `api_server.py`

**Why:** Current implementation blocks event loop, can't handle concurrent requests.

**Tasks:**
- [ ] Wrap `pipeline.process()` in `run_in_executor`
- [ ] Add request timeout handling
- [ ] Add concurrent request limit

**Implementation:**
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # Run blocking pipeline in thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor,
        pipeline.process,
        user_message
    )
    # ... rest of handler
```

---

### 2.2 Add Input Validation & Rate Limiting
**File:** `api_server.py`, `src/validation.py`

**Why:** Prevent abuse and ensure system stability.

**Tasks:**
- [ ] Add input length validation (max 2000 chars)
- [ ] Add rate limiting middleware (e.g., slowapi)
- [ ] Sanitize input for potential injection
- [ ] Add request timeout (30s max)

**Implementation:**
```python
# src/validation.py
from fastapi import HTTPException

MAX_MESSAGE_LENGTH = 2000
MIN_MESSAGE_LENGTH = 2

def validate_message(message: str) -> str:
    """Validate and sanitize user message."""
    if not message or len(message.strip()) < MIN_MESSAGE_LENGTH:
        raise HTTPException(400, "Съобщението е твърде кратко")

    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(400, "Съобщението е твърде дълго (макс. 2000 символа)")

    # Strip control characters
    message = ''.join(char for char in message if char.isprintable() or char in '\n\t')

    return message.strip()
```

**Rate Limiting:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/v1/chat/completions")
@limiter.limit("10/minute")  # 10 requests per minute per IP
async def chat_completions(request: Request, ...):
    ...
```

---

### 2.3 Create Centralized Config
**File:** `src/config.py`

**Why:** Hardcoded values are hard to change and environment-specific.

**Tasks:**
- [ ] Create `src/config.py` with pydantic-settings
- [ ] Move all hardcoded values to config
- [ ] Support `.env` file and environment variables
- [ ] Add config validation on startup

**Implementation:**
```python
# src/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    # Models
    medgemma_model_path: str = "./models/medgemma-4b-it-bf16"
    medgemma_max_tokens: int = 200
    medgemma_temperature: float = 0.3

    # Database
    chromadb_path: str = "data/chromadb"

    # Product
    product_base_url: str = "https://viapharma.us/products"

    # Limits
    max_message_length: int = 2000
    rate_limit_per_minute: int = 10
    request_timeout_seconds: int = 30

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    class Config:
        env_file = ".env"
        env_prefix = "VIAPHARMA_"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

---

## Phase 3: Quality & Reliability (P2) - Week 3

### 3.1 Add Integration Tests
**File:** `tests/test_pipeline.py`, `tests/test_api.py`

**Tasks:**
- [ ] Test full pipeline flow with mock MedGemma
- [ ] Test API endpoints with TestClient
- [ ] Test error handling paths
- [ ] Test edge cases (empty input, very long input, special characters)

**Implementation:**
```python
# tests/test_api.py
from fastapi.testclient import TestClient
from api_server import app

client = TestClient(app)

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_chat_completion():
    response = client.post("/v1/chat/completions", json={
        "model": "viapharma-medgemma",
        "messages": [{"role": "user", "content": "Имам главоболие"}]
    })
    assert response.status_code == 200
    assert "choices" in response.json()

def test_empty_message():
    response = client.post("/v1/chat/completions", json={
        "model": "viapharma-medgemma",
        "messages": [{"role": "user", "content": ""}]
    })
    assert response.status_code == 400
```

---

### 3.2 Pre-warm Models on Startup
**File:** `api_server.py`

**Tasks:**
- [ ] Add startup event to pre-load models
- [ ] Add health check endpoint with model status
- [ ] Add graceful shutdown

**Implementation:**
```python
@app.on_event("startup")
async def startup_event():
    """Pre-warm models for faster first request."""
    logger.info("Pre-warming models...")

    # Load pipeline and models in background thread
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _warmup_models)

    logger.info("Models ready!")

def _warmup_models():
    pipeline = get_pipeline()
    pipeline.medical_model  # Trigger MedGemma load
    pipeline.translator.load_all()  # Load both translation models
    pipeline.product_store  # Initialize ChromaDB

@app.get("/health")
async def health_check():
    """Detailed health check with model status."""
    pipeline = get_pipeline()
    return {
        "status": "healthy",
        "models": {
            "medgemma": pipeline._medical_model is not None,
            "translator_bg_en": pipeline._translator._bg_to_en_model is not None,
            "translator_en_bg": pipeline._translator._en_to_bg_model is not None,
        },
        "products": pipeline.product_store.collection.count(),
    }
```

---

### 3.3 Update Documentation
**Files:** `README.md`, `OPEN_WEBUI_SETUP.md`, `ARCHITECTURE.md`

**Tasks:**
- [ ] Create `README.md` with quick start guide
- [ ] Remove Gradio references from `OPEN_WEBUI_SETUP.md`
- [ ] Add `/hints` endpoint to `ARCHITECTURE.md`
- [ ] Add environment variables documentation
- [ ] Add troubleshooting section

---

## Phase 4: Polish (P3) - Week 4

### 4.1 Replace Cache with LRU
**File:** `src/translator.py`

**Tasks:**
- [ ] Replace manual dict cache with `functools.lru_cache`
- [ ] Or implement proper LRU eviction

**Implementation:**
```python
from collections import OrderedDict

class LRUCache:
    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.max_size = max_size

    def get(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key, value):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)
        self.cache[key] = value
```

---

### 4.2 Add Detailed Health Check
**File:** `api_server.py`

**Tasks:**
- [ ] Add `/health` endpoint with model status
- [ ] Add `/metrics` endpoint for monitoring
- [ ] Track request latency, error rates

---

## Test Coverage Goals

| Module | Target Coverage |
|--------|-----------------|
| `safety.py` | 100% |
| `intent_classifier.py` | 90% |
| `pipeline.py` | 80% |
| `api_server.py` | 80% |
| `translator.py` | 70% |
| `product_store.py` | 70% |
| `medical_model.py` | 70% |

---

## Dependencies to Add

```txt
# requirements.txt additions
pytest>=7.0.0           # Testing
pytest-asyncio>=0.21.0  # Async test support
pytest-cov>=4.0.0       # Coverage reporting
httpx>=0.24.0           # Async HTTP client for tests
slowapi>=0.1.8          # Rate limiting
pydantic-settings>=2.0  # Config management
```

---

## Definition of Done

### Phase 1 Complete When:
- [ ] All safety layer tests pass
- [ ] Logging visible in console during requests
- [ ] No `print()` statements remain in production code

### Phase 2 Complete When:
- [ ] API handles 10 concurrent requests without blocking
- [ ] Invalid inputs return proper error messages
- [ ] All config from environment variables

### Phase 3 Complete When:
- [ ] Integration tests pass
- [ ] First request < 3s (models pre-warmed)
- [ ] Documentation is accurate and complete

### Phase 4 Complete When:
- [ ] Cache properly evicts old entries
- [ ] Health endpoint shows all model statuses
- [ ] Test coverage meets targets

---

## Estimated Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1 | 3-4 days | None |
| Phase 2 | 3-4 days | Phase 1 logging |
| Phase 3 | 3-4 days | Phase 2 config |
| Phase 4 | 2-3 days | Phase 3 tests |

**Total:** ~2-3 weeks for production-ready system
