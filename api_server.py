"""
ViaPharma OTC Chatbot - OpenAI-Compatible API Server

Exposes the pipeline as an OpenAI-compatible API for integration
with Open WebUI and other OpenAI-compatible clients.
"""

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.config import get_settings
from src.logging_config import (
    get_logger,
    hash_for_audit,
    init_default_logger,
    log_medical_query,
    set_request_id,
)
from src.pipeline import get_pipeline

# Load settings
settings = get_settings()

# Initialize logging
init_default_logger(level=settings.log_level, json_format=settings.log_json)
logger = get_logger("viapharma.api")

# Thread pool for running blocking operations
executor = ThreadPoolExecutor(max_workers=4)

# Rate limiting storage (simple in-memory implementation)
rate_limit_store: dict[str, list[float]] = {}

# Metrics tracking
metrics_store = {
    "requests_total": 0,
    "requests_success": 0,
    "requests_failed": 0,
    "requests_medical": 0,
    "requests_non_medical": 0,
    "requests_red_flag": 0,
    "total_latency_ms": 0.0,
}


# =============================================================================
# Input Validation
# =============================================================================

def validate_message(message: str) -> str:
    """Validate and sanitize user message, raising HTTPException if invalid."""
    if not message:
        raise HTTPException(status_code=400, detail="Съобщението е празно")

    message = message.strip()

    if len(message) < settings.min_message_length:
        raise HTTPException(
            status_code=400,
            detail=f"Съобщението е твърде кратко (мин. {settings.min_message_length} символа)"
        )

    if len(message) > settings.max_message_length:
        raise HTTPException(
            status_code=400,
            detail=f"Съобщението е твърде дълго (макс. {settings.max_message_length} символа)"
        )

    # Strip control characters (keep newlines and tabs)
    return ''.join(char for char in message if char.isprintable() or char in '\n\t')


def check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit. Returns True if within limit."""
    if not settings.enable_rate_limiting:
        return True

    now = time.time()
    window_start = now - 60

    if client_ip not in rate_limit_store:
        rate_limit_store[client_ip] = []

    # Remove old entries and check limit
    rate_limit_store[client_ip] = [ts for ts in rate_limit_store[client_ip] if ts > window_start]

    if len(rate_limit_store[client_ip]) >= settings.rate_limit_per_minute:
        return False

    rate_limit_store[client_ip].append(now)
    return True


def get_client_ip(request: Request) -> str:
    """Get client IP from request, handling proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# =============================================================================
# API Models (OpenAI-compatible)
# =============================================================================


class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "viapharma-medgemma"
    messages: list[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False


class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: str


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str
    description: str = ""
    meta: dict = {}


class ModelsResponse(BaseModel):
    object: str = "list"
    data: list[ModelInfo]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    models_loaded: dict
    products_count: int
    uptime_seconds: float


# =============================================================================
# System Prompt and Hints
# =============================================================================

SYSTEM_PROMPT = """Вие сте ViaPharma Аптечен Асистент - виртуален фармацевтичен консултант за viapharma.us.

Вашата роля:
- Разбирате симптоми, описани на български език
- Препоръчвате подходящи продукти без рецепта (OTC)
- Давате информация за дозировка и предупреждения
- Винаги напомняте, че не замествате консултация с лекар

Важно:
- Отговаряйте САМО на български език
- При сериозни симптоми (болки в гърдите, затруднено дишане, силни главоболия) - насочвайте към лекар
- Препоръчвайте САМО продукти без рецепта
"""

MODEL_HINTS = [
    "Имам главоболие и се чувствам уморен",
    "Какво да взема за настинка?",
    "Боли ме гърлото от няколко дни",
    "Имам стомашни болки и гадене",
    "Търся нещо за алергия",
    "Какво помага при безсъние?",
    "Имам болки в мускулите след тренировка",
    "Търся витамини за имунитет",
]

MODEL_DESCRIPTION = "Аптечен асистент за препоръки на продукти без рецепта. Опишете вашите симптоми на български език."


# =============================================================================
# Application Lifecycle
# =============================================================================

# Track startup time for uptime calculation
startup_time: float = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    global startup_time
    startup_time = time.time()

    logger.info("=" * 60)
    logger.info("ViaPharma Аптечен Асистент - API Сървър")
    logger.info("=" * 60)

    # Pre-warm models if configured
    if settings.prewarm_models:
        logger.info("Pre-warming models...")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, _warmup_models)
        logger.info("Models ready!")

    logger.info("OpenAI-съвместими endpoints:")
    logger.info("  GET  /v1/models           (списък модели)")
    logger.info("  POST /v1/chat/completions (чат)")
    logger.info("  GET  /health              (статус)")
    logger.info("  GET  /hints               (примерни въпроси)")
    logger.info(f"Свържете Open WebUI към: http://localhost:{settings.api_port}/v1")
    logger.info("=" * 60)

    yield

    # Cleanup
    logger.info("Shutting down...")
    executor.shutdown(wait=False)


def _warmup_models():
    """Pre-load models (runs in thread pool)."""
    try:
        pipeline = get_pipeline()
        # Trigger lazy loading of each component
        _ = pipeline.medical_model
        _ = pipeline.translator
        pipeline.translator.load_all()
        _ = pipeline.product_store
    except Exception as e:
        logger.error(f"Failed to pre-warm models: {e}")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="ViaPharma Аптечен Асистент",
    description="API за аптечен чатбот - препоръки за продукти без рецепта на български език",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Open WebUI and viapharma.us
# Parse allowed origins from config (comma-separated)
cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _is_chat_endpoint(path: str) -> bool:
    """Check if path is a chat endpoint."""
    return "/chat/" in path or "/completions" in path


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Log requests and handle rate limiting."""
    request_id = set_request_id()
    client_ip = get_client_ip(request)
    start_time = time.time()
    is_chat = _is_chat_endpoint(request.url.path)

    # Check rate limit for chat endpoints
    if is_chat and not check_rate_limit(client_ip):
        logger.warning("Rate limit exceeded", extra={"client_ip": client_ip})
        return JSONResponse(
            status_code=429,
            content={"detail": "Твърде много заявки. Моля, изчакайте минута."}
        )

    if settings.enable_request_logging:
        logger.info("Request started", extra={
            "method": request.method,
            "path": request.url.path,
            "client_ip": client_ip,
            "request_id": request_id
        })

    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    if is_chat:
        metrics_store["total_latency_ms"] += duration_ms

    if settings.enable_request_logging:
        logger.info("Request completed", extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "request_id": request_id
        })

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
    return response


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/")
async def root():
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "service": "ViaPharma Аптечен Асистент",
        "description": MODEL_DESCRIPTION,
        "language": "bg"
    }


@app.get("/health/live")
async def liveness():
    """Kubernetes liveness probe. Returns 200 if process is alive."""
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe. Returns 200 if models loaded, 503 otherwise."""
    pipeline = get_pipeline()

    medgemma_ready = pipeline._medical_model is not None and pipeline._medical_model._loaded
    if not medgemma_ready:
        raise HTTPException(status_code=503, detail="MedGemma model not loaded")

    try:
        products_count = pipeline.product_store.collection.count()
        if products_count == 0:
            raise HTTPException(status_code=503, detail="Product store empty or not initialized")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Product store empty or not initialized")

    return {"status": "ready", "models": {"medgemma": medgemma_ready}, "products_count": products_count}


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Detailed health check with model status."""
    pipeline = get_pipeline()

    models_loaded = {
        "medgemma": pipeline._medical_model is not None and pipeline._medical_model._loaded,
        "translator_bg_en": pipeline._translator is not None and pipeline._translator._bg_to_en_model is not None,
        "translator_en_bg": pipeline._translator is not None and pipeline._translator._en_to_bg_model is not None,
    }

    try:
        products_count = pipeline.product_store.collection.count()
    except Exception:
        products_count = 0

    return HealthResponse(
        status="healthy" if any(models_loaded.values()) else "starting",
        service="ViaPharma Аптечен Асистент",
        version="1.0.0",
        models_loaded=models_loaded,
        products_count=products_count,
        uptime_seconds=round(time.time() - startup_time, 2) if startup_time else 0,
    )


@app.get("/hints")
async def get_hints():
    """Get suggested medical queries in Bulgarian for UI display."""
    return {
        "hints": MODEL_HINTS,
        "placeholder": "Опишете вашите симптоми...",
        "welcome_message": "Здравейте! Аз съм вашият аптечен асистент. Как мога да ви помогна днес?",
        "examples_title": "Примерни въпроси:",
    }


@app.get("/metrics")
async def get_metrics():
    """Get application metrics for monitoring."""
    pipeline = get_pipeline()

    avg_latency = (
        metrics_store["total_latency_ms"] / metrics_store["requests_total"]
        if metrics_store["requests_total"] > 0
        else 0.0
    )

    cache_stats = _get_cache_stats(pipeline)

    try:
        products_count = pipeline.product_store.collection.count()
    except Exception:
        products_count = 0

    return JSONResponse(content={
        "requests": {
            "total": int(metrics_store["requests_total"]),
            "success": int(metrics_store["requests_success"]),
            "failed": int(metrics_store["requests_failed"]),
            "medical": int(metrics_store["requests_medical"]),
            "non_medical": int(metrics_store["requests_non_medical"]),
            "red_flag": int(metrics_store["requests_red_flag"]),
        },
        "latency": {
            "average_ms": round(float(avg_latency), 2),
            "total_ms": round(float(metrics_store["total_latency_ms"]), 2),
        },
        "cache": cache_stats,
        "products_count": int(products_count),
        "uptime_seconds": round(time.time() - startup_time, 2) if startup_time else 0,
        "rate_limit_ips_tracked": len(rate_limit_store),
    })


def _get_cache_stats(pipeline) -> dict:
    """Get all cache stats (translator and medical model)."""
    result = {}

    # Translator cache stats
    if pipeline._translator is not None and hasattr(pipeline._translator, 'get_cache_stats'):
        try:
            stats = pipeline._translator.get_cache_stats()
            if isinstance(stats, dict):
                result["translator"] = {
                    "bg_to_en": dict(stats.get("bg_to_en", {})) if stats.get("bg_to_en") else None,
                    "en_to_bg": dict(stats.get("en_to_bg", {})) if stats.get("en_to_bg") else None,
                }
        except Exception:
            pass

    # Medical model (MedGemma) cache stats
    if pipeline._medical_model is not None and hasattr(pipeline._medical_model, 'get_cache_stats'):
        try:
            result["medical_reasoning"] = pipeline._medical_model.get_cache_stats()
        except Exception:
            pass

    return result if result else None


@app.get("/v1/models", response_model=ModelsResponse)
@app.get("/models", response_model=ModelsResponse)
async def list_models():
    """List available models (OpenAI-compatible)."""
    return ModelsResponse(
        data=[
            ModelInfo(
                id="viapharma-medgemma",
                created=int(time.time()),
                owned_by="viapharma",
                description=MODEL_DESCRIPTION,
                meta={
                    "hints": MODEL_HINTS,
                    "language": "bg",
                    "category": "medical",
                }
            )
        ]
    )


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
@app.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest, req: Request):
    """OpenAI-compatible chat completions endpoint."""
    user_message = _extract_user_message(request.messages)
    if not user_message:
        logger.warning("No user message in request")
        raise HTTPException(status_code=400, detail="Няма съобщение от потребителя")

    user_message = validate_message(user_message)
    logger.info("Chat request", extra={
        "model": request.model,
        "message_length": len(user_message),
        "stream": request.stream
    })

    if request.stream:
        return await _stream_response(user_message, request.model)

    result = await _process_with_timeout(user_message)

    logger.debug("Pipeline result", extra={
        "is_medical": result.is_medical,
        "is_red_flag": result.is_red_flag,
        "response_length": len(result.response)
    })

    _update_metrics(result)
    _log_audit(user_message, result, get_client_ip(req))

    return _build_chat_response(request, result)


def _extract_user_message(messages: list[Message]) -> str | None:
    """Extract the last user message from the message list."""
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    return None


async def _process_with_timeout(user_message: str):
    """Process message through pipeline with timeout handling."""
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(executor, _process_message, user_message),
            timeout=settings.request_timeout_seconds
        )
    except asyncio.TimeoutError:
        logger.error("Request timed out")
        metrics_store["requests_total"] += 1
        metrics_store["requests_failed"] += 1
        raise HTTPException(
            status_code=504,
            detail="Заявката отне твърде дълго. Моля, опитайте отново."
        )


def _update_metrics(result) -> None:
    """Update metrics based on pipeline result."""
    metrics_store["requests_total"] += 1
    metrics_store["requests_success"] += 1
    if result.is_medical:
        metrics_store["requests_medical"] += 1
    else:
        metrics_store["requests_non_medical"] += 1
    if result.is_red_flag:
        metrics_store["requests_red_flag"] += 1


def _log_audit(user_message: str, result, client_ip: str) -> None:
    """Log medical query for compliance audit."""
    product_skus = []
    if hasattr(result, 'selected_products') and result.selected_products:
        for p in result.selected_products:
            sku = getattr(p, 'id', None) or getattr(p, 'sku', None)
            if sku:
                product_skus.append(str(sku))

    log_medical_query(
        query_hash=hash_for_audit(user_message),
        is_medical=result.is_medical,
        is_red_flag=result.is_red_flag,
        products_recommended=product_skus,
        safety_severity="red_flag" if result.is_red_flag else "none",
        response_length=len(result.response),
        client_ip_hash=hash_for_audit(client_ip),
    )


def _build_chat_response(request: ChatCompletionRequest, result) -> ChatCompletionResponse:
    """Build OpenAI-compatible chat completion response."""
    prompt_tokens = sum(len(m.content.split()) * 2 for m in request.messages)
    completion_tokens = len(result.response.split()) * 2

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:8]}",
        created=int(time.time()),
        model=request.model,
        choices=[
            Choice(
                index=0,
                message=Message(role="assistant", content=result.response),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def _process_message(user_message: str):
    """Process message through pipeline (runs in thread pool)."""
    pipeline = get_pipeline()
    return pipeline.process(user_message)


async def _stream_response(user_message: str, model: str):
    """Stream response in SSE format (OpenAI streaming format)."""

    async def generate():
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, _process_message, user_message),
                timeout=settings.request_timeout_seconds
            )
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'error': {'message': 'Заявката отне твърде дълго', 'type': 'timeout_error'}}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        created = int(time.time())

        words = result.response.split(" ")
        for i, word in enumerate(words):
            chunk_content = word + (" " if i < len(words) - 1 else "")
            chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": chunk_content}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        final_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="warning"
    )
