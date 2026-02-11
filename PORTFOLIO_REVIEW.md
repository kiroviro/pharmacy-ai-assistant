# ViaPharma MedGemma - Production & Portfolio Review

**Reviewer Context:** Staff engineer review for production deployment and public portfolio visibility
**Repository:** ViaPharma OTC Chatbot
**Date:** 2026-02-11

---

## Executive Summary

This is a **well-architected medical chatbot** with strong safety features and clean code. The commit history tells a coherent story of iterative improvement. However, several gaps exist for both production readiness and portfolio polish.

**Overall Grade: B+**
- Production Readiness: B
- Code Quality: A-
- Portfolio Impression: B
- Domain Safety: A-

---

## 1. Production Readiness Issues

### 🔴 CRITICAL

#### 1.1 No HTTPS/TLS Configuration
**File:** `api_server.py`, `OPEN_WEBUI_SETUP.md`
**Issue:** API runs on plain HTTP. Medical/health data should never traverse unencrypted connections.
**Why it matters:** HIPAA-adjacent concerns, user trust, data integrity.
**Fix:**
```python
# Add to api_server.py or use reverse proxy (nginx/traefik)
if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        ssl_keyfile="path/to/key.pem",
        ssl_certfile="path/to/cert.pem",
    )
```

#### 1.2 No Authentication/Authorization
**File:** `api_server.py`
**Issue:** API is completely open. Anyone can send requests.
**Why it matters:** Abuse prevention, rate limiting by user, audit trails.
**Fix:** Add API key validation or JWT authentication:
```python
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

#### 1.3 Secrets in Code/Hardcoded Paths
**File:** `src/medical_model.py:460`, `src/product_store.py:24`
**Issue:** Hardcoded paths like `./models/medgemma-4b-it-bf16` and `data/chromadb`.
**Why it matters:** Deployment flexibility, 12-factor app principles.
**Fix:** Already have config.py - use it consistently:
```python
# In medical_model.py
from src.config import get_settings
settings = get_settings()
model_path = settings.medgemma_model_path
```

---

### 🟠 HIGH

#### 1.4 No Health Check Liveness/Readiness Separation
**File:** `api_server.py:355`
**Issue:** Single `/health` endpoint. Kubernetes needs separate liveness and readiness probes.
**Why it matters:** Prevents restart loops during model loading.
**Fix:**
```python
@app.get("/health/live")
async def liveness():
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness():
    # Check if models are loaded
    pipeline = get_pipeline()
    if not pipeline._medical_model or not pipeline._medical_model._loaded:
        raise HTTPException(503, "Models not ready")
    return {"status": "ready"}
```

#### 1.5 No Request ID Propagation to Logs
**File:** `src/logging_config.py`
**Issue:** Request IDs are generated but not consistently propagated through all log calls.
**Why it matters:** Distributed tracing, debugging production issues.
**Fix:** Already have `set_request_id()` - ensure all components use `get_request_id()` in log extra.

#### 1.6 Rate Limiter State Lost on Restart
**File:** `api_server.py:35`
**Issue:** `rate_limit_store: dict` is in-memory only.
**Why it matters:** Restart clears rate limits; attackers can exploit this.
**Fix:** Use Redis for production or add startup grace period:
```python
# Consider: slowapi with Redis backend
# Or: Add VIAPHARMA_RATE_LIMIT_BACKEND=redis config option
```

#### 1.7 No Graceful Shutdown for ThreadPoolExecutor
**File:** `api_server.py:258`
**Issue:** `executor.shutdown(wait=False)` - doesn't wait for in-flight requests.
**Why it matters:** Requests may be dropped on deployment.
**Fix:**
```python
executor.shutdown(wait=True, cancel_futures=False)
```

---

### 🟡 MEDIUM

#### 1.8 Missing Request Timeout at HTTP Level
**Issue:** `asyncio.wait_for` timeout exists but no overall HTTP timeout.
**Fix:** Add `uvicorn --timeout-keep-alive` or use middleware.

#### 1.9 No Error Tracking/Alerting Integration
**Issue:** No Sentry, Datadog, or similar integration.
**Fix:** Add Sentry SDK:
```python
import sentry_sdk
sentry_sdk.init(dsn=settings.sentry_dsn)
```

#### 1.10 Print Statements in Production Code
**Files:** `src/product_store.py:96-97`, `src/pipeline.py:483`
**Issue:** Multiple `print()` statements instead of logger.
**Fix:** Replace with `logger.info()` or `logger.debug()`.

#### 1.11 No CORS Origin Restriction
**File:** `api_server.py:288`
**Issue:** `allow_origins=["*"]` allows any origin.
**Fix:** Restrict to known domains:
```python
allow_origins=["https://viapharma.us", "http://localhost:3000"]
```

---

### 🟢 LOW

#### 1.12 Dependencies Not Pinned
**File:** `requirements.txt`
**Issue:** Version ranges like `>=0.19.0` instead of exact versions.
**Fix:** Use `pip freeze > requirements.lock` for reproducible builds.

#### 1.13 No Dockerfile
**Issue:** No containerization config for deployment.
**Fix:** Add `Dockerfile` and `docker-compose.yml`.

---

## 2. Code Quality & Architecture Issues

### 🟠 HIGH

#### 2.1 Global Mutable State Pattern
**Files:** `src/pipeline.py:590`, `src/translator.py:207`, etc.
**Issue:** Multiple `_global_instance: Optional[X] = None` patterns. Not thread-safe for initialization.
**Fix:** Use proper singleton pattern or dependency injection:
```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_pipeline() -> Pipeline:
    return Pipeline()
```

#### 2.2 Missing Type Hints in Some Functions
**Files:** `src/data_loader.py`, `src/product_store.py`
**Issue:** Inconsistent type annotations.
**Fix:** Add comprehensive type hints and run `mypy`.

---

### 🟡 MEDIUM

#### 2.3 Test File Not Committed
**File:** `tests/test_pharmacy_questions.py`
**Issue:** Untracked test file - either commit or delete.
**Fix:** `git add tests/test_pharmacy_questions.py` or `rm tests/test_pharmacy_questions.py`

#### 2.4 Dead Files in Output Directory
**Files:** `output/improvement_plan_*.md`, `output/test_results_*.json`
**Issue:** Generated files cluttering repo.
**Fix:** Add `output/` to `.gitignore` or clean up.

#### 2.5 No Type Checking in CI
**Issue:** No `mypy` or `pyright` configuration.
**Fix:** Add `pyproject.toml` with mypy config.

---

## 3. Portfolio / Recruiter Impression Issues

### 🔴 CRITICAL

#### 3.1 No CI/CD Configuration
**Issue:** No `.github/workflows/` directory. Recruiters expect automated testing.
**Fix:** Add GitHub Actions:
```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v --cov=src
```

#### 3.2 No Architecture Diagram in README
**Issue:** ARCHITECTURE.md has ASCII diagram but README doesn't show it.
**Fix:** Add Mermaid diagram to README:
```markdown
## Architecture
```mermaid
flowchart LR
    A[User Input BG] --> B[Intent Classifier]
    B --> C[Translate BG→EN]
    C --> D[MedGemma Reasoning]
    D --> E[Safety Check]
    E --> F[Product RAG]
    F --> G[Response BG]
```
```

---

### 🟠 HIGH

#### 3.3 README Missing Key Sections
**Issue:** No badges, no demo gif, no contributing guide, no architecture overview.
**Fix:** Add:
- Build status badge (after adding CI)
- Demo GIF showing the chatbot in action
- Quick architecture diagram
- "How it works" section

#### 3.4 No API Documentation
**Issue:** No OpenAPI/Swagger docs link in README.
**Fix:** FastAPI auto-generates these. Add to README:
```markdown
## API Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
```

#### 3.5 License Unclear
**File:** `README.md:100`
**Issue:** "Proprietary - ViaPharma" is vague. Recruiters can't assess open-source-ability.
**Fix:** Either use standard license (MIT, Apache) or clarify terms.

---

### 🟡 MEDIUM

#### 3.6 No Contributing Guide
**Issue:** Missing `CONTRIBUTING.md`.
**Fix:** Add standard contributing guidelines.

#### 3.7 Commit History Could Be Cleaner
**Issue:** Some commits like `chore: Add test artifacts to .gitignore` could be squashed.
**Assessment:** Current history is actually quite clean with good conventional commit format. Minor issue.

#### 3.8 No Performance Benchmarks
**Issue:** No documented latency numbers or throughput metrics.
**Fix:** Add to README:
```markdown
## Performance
- Average response time: ~2-3s (cold) / ~500ms (warm)
- Supports 10 concurrent requests
- Memory usage: ~8GB (with models loaded)
```

---

## 4. Pharmacy / Domain-Specific Concerns

### 🟠 HIGH

#### 4.1 No Audit Logging for Medical Queries
**Issue:** No persistent log of what medical advice was given.
**Why it matters:** Regulatory compliance, liability protection.
**Fix:** Add structured audit log:
```python
# Log to separate audit file/database
audit_logger.info("medical_advice", extra={
    "request_id": request_id,
    "query_hash": hash(user_message),  # Privacy-preserving
    "products_recommended": [p.sku for p in products],
    "safety_flags": result.is_red_flag,
    "timestamp": datetime.utcnow().isoformat(),
})
```

#### 4.2 No User Data Retention Policy
**Issue:** No documentation on what user data is stored/logged.
**Fix:** Add `PRIVACY.md` documenting:
- What is logged (queries, IPs, timestamps)
- Retention period
- GDPR compliance (if serving EU users)

#### 4.3 Product Pricing Not Real-Time
**File:** `src/data_loader.py:18`
**Issue:** Static BGN_TO_EUR conversion rate. Prices from CSV may be stale.
**Fix:** Add disclaimer or implement real-time pricing API.

---

### 🟡 MEDIUM

#### 4.4 No Product Availability Check
**Issue:** Recommends products without checking stock.
**Fix:** Add stock_status field to product data or integrate with inventory API.

#### 4.5 Drug Interaction Warnings Not Implemented
**Issue:** No checking for multi-product interactions.
**Fix:** Consider adding drug interaction database for future enhancement.

---

## Summary: Priority Action Items

### Top 5 Things to Fix Before Going Live

1. **Add HTTPS/TLS** - Critical for medical data protection
2. **Add API Authentication** - Prevent abuse and enable audit trails
3. **Add Liveness/Readiness Probes** - Required for Kubernetes deployment
4. **Add Audit Logging** - Medical regulatory requirement
5. **Fix CORS Configuration** - Restrict to viapharma.us domain

### Top 5 Things to Add to Impress Recruiters

1. **GitHub Actions CI/CD** - Shows DevOps maturity
2. **Architecture Diagram in README** - Visual communication skills
3. **Dockerfile + docker-compose** - Production deployment awareness
4. **API Documentation Link** - Developer experience focus
5. **Performance Benchmarks** - Quantitative thinking

---

## Positive Highlights (What's Done Well)

✅ **Excellent safety layer** - Comprehensive emergency/urgent symptom detection
✅ **Clean commit history** - Conventional commits, logical progression
✅ **Good test coverage** - 79 tests, 95% safety coverage
✅ **Proper logging infrastructure** - Structured logging with request IDs
✅ **Bilingual support** - Bulgarian + English throughout
✅ **Two-stage RAG** - Sophisticated retrieval architecture
✅ **Rate limiting** - Basic protection in place
✅ **LRU cache** - Performance optimization
✅ **Centralized config** - pydantic-settings based
✅ **Good documentation** - ARCHITECTURE.md is thorough

---

*This review was conducted as a portfolio/production readiness assessment. Issues are prioritized by business impact and recruiter perception.*
