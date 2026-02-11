# ViaPharma MedGemma - Technical Review

**Date:** 2026-02-11
**Reviewer:** Staff Engineer
**Version:** 1.0

---

## Executive Summary

Solid MVP with good architecture. Key gaps: **no tests**, **no logging**, **limited error handling**, and **production hardening** needed.

**Grade: B-** (Good MVP, not production-ready)

---

## 1. Architecture (Good)

### Strengths
- Clean separation of concerns (pipeline pattern)
- Two-stage retrieval is smart (Perplexity pattern)
- Lazy loading for faster startup
- Global singletons for resource sharing

### Improvements

| Issue | Recommendation |
|-------|----------------|
| Tight coupling | Use dependency injection instead of `get_*()` globals |
| No async in pipeline | MedGemma is blocking - consider async wrapper for API |
| Single-threaded | Pipeline can't handle concurrent requests efficiently |

---

## 2. Testing (Critical Gap)

### Current State
`tests/` directory is empty

### Needed Structure
```
tests/
├── test_intent_classifier.py   # Unit tests
├── test_safety.py              # Red-flag detection
├── test_translator.py          # Translation accuracy
├── test_pipeline.py            # Integration tests
├── test_api_server.py          # API endpoint tests
└── conftest.py                 # Fixtures
```

### Priority Tests
1. **Safety layer** - must catch all emergency symptoms
2. **Intent classifier** - no false negatives for medical queries
3. **API responses** - correct format for Open WebUI

---

## 3. Error Handling (Needs Work)

### Current Issues
```python
# medical_model.py:240 - Silent failure
except (json.JSONDecodeError, ValueError) as e:
    print(f"Warning: Failed to parse JSON response: {e}")

# product_store.py:106 - Swallowed exception
except Exception:
    pass
```

### Recommendations
- Add structured logging (not print statements)
- Create custom exceptions (`MedGemmaParseError`, `ProductStoreError`)
- Return error responses to user instead of silent fallbacks

---

## 4. Security (Medium Risk)

| Risk | Severity | Fix |
|------|----------|-----|
| No input length limit | Medium | Add max length validation |
| No rate limiting | Medium | Add rate limiter middleware |
| CORS allows all origins | Low | Restrict in production |
| No API authentication | Low | Add API key validation |

### Recommended Input Validation
```python
# api_server.py - Add input validation
MAX_MESSAGE_LENGTH = 2000

if len(user_message) > MAX_MESSAGE_LENGTH:
    raise HTTPException(400, "Съобщението е твърде дълго")
```

---

## 5. Performance (Opportunities)

| Bottleneck | Current | Improvement |
|------------|---------|-------------|
| MedGemma inference | ~2-5s | Pre-warm on startup |
| Translation models | ~500ms first call | Pre-load both models |
| ChromaDB search | ~50ms | Already good |
| Response streaming | Fake streaming | True token streaming |

### Quick Win: Pre-warm Models
```python
# api_server.py - Pre-warm models on startup
@app.on_event("startup")
async def warmup():
    pipeline = get_pipeline()
    pipeline.medical_model  # Trigger load
    pipeline.translator.load_all()
```

---

## 6. Observability (Missing)

### Current State
No logging/monitoring infrastructure

### Recommended Implementation
```python
import logging
import time

logger = logging.getLogger("viapharma")

# In pipeline.process():
start = time.time()
logger.info(f"Processing query", extra={
    "query_length": len(user_input),
    "is_medical": is_medical,
})
# ... processing ...
logger.info(f"Completed", extra={
    "duration_ms": (time.time() - start) * 1000,
    "products_found": len(selected_products),
})
```

---

## 7. Configuration (Hardcoded Values)

### Currently Hardcoded
```python
# Various files:
PRODUCT_BASE_URL = "https://viapharma.us/products"  # pipeline.py
DB_PATH = "data/chromadb"                           # product_store.py
MAX_TOKENS = 200                                    # medical_model.py
```

### Recommended: Create `config.py`
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    product_base_url: str = "https://viapharma.us/products"
    chromadb_path: str = "data/chromadb"
    medgemma_model_path: str = "./models/medgemma-4b-it-bf16"
    max_tokens: int = 200
    api_port: int = 8000

    class Config:
        env_file = ".env"
```

---

## 8. Documentation (Update Needed)

| File | Issue |
|------|-------|
| `OPEN_WEBUI_SETUP.md` | References deleted `app_gradio.py` |
| `ARCHITECTURE.md` | Missing new `/hints` endpoint |
| No `README.md` | Project needs entry point doc |

---

## 9. Code Issues Found

### 1. Cache Doesn't Evict (translator.py:86)
```python
if len(self._cache_bg_to_en) < self._cache_max_size:
    self._cache_bg_to_en[text] = result
# Problem: Once full, no new entries cached. Use LRU instead.
```

### 2. Non-deterministic Product IDs (product_store.py:126)
```python
product_id = product.sku if product.sku else f"product_{i}"
# Problem: Index-based IDs change if product order changes
```

### 3. Blocking IO in Async Handler (api_server.py:201)
```python
result = pipeline.process(user_message)  # Blocks event loop
# Should use: await run_in_executor(None, pipeline.process, user_message)
```

---

## 10. Priority Roadmap

| Priority | Task | Effort |
|----------|------|--------|
| **P0** | Add unit tests for safety layer | 1 day |
| **P0** | Add logging infrastructure | 0.5 day |
| **P1** | Fix async blocking in API | 0.5 day |
| **P1** | Add input validation & rate limiting | 0.5 day |
| **P1** | Create config.py | 0.5 day |
| **P2** | Add integration tests | 1 day |
| **P2** | Pre-warm models on startup | 0.5 day |
| **P2** | Update documentation | 0.5 day |
| **P3** | Replace cache with LRU | 0.5 day |
| **P3** | Add health check endpoint with model status | 0.5 day |

---

## Must Fix Before Production

1. Tests for safety-critical code
2. Structured logging
3. Async handling for concurrent requests
4. Input validation

---

## Files Reviewed

- `api_server.py` - OpenAI-compatible API
- `src/pipeline.py` - Main orchestrator
- `src/medical_model.py` - MedGemma wrapper
- `src/translator.py` - MarianMT translation
- `src/product_store.py` - ChromaDB vector search
- `src/safety.py` - Red-flag detection
- `src/intent_classifier.py` - Medical query detection
- `src/data_loader.py` - CSV loader
- `ARCHITECTURE.md` - Architecture documentation
- `OPEN_WEBUI_SETUP.md` - Setup guide
- `requirements.txt` - Dependencies
