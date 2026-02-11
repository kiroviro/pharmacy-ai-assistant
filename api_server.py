"""
ViaPharma OTC Chatbot - OpenAI-Compatible API Server

This server exposes the pipeline as an OpenAI-compatible API,
allowing integration with Open WebUI and other OpenAI-compatible clients.
"""

import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.pipeline import get_pipeline

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


# =============================================================================
# System Prompt (Bulgarian medical assistant context)
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

# Bulgarian medical hints - suggested queries for UI
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
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="ViaPharma Аптечен Асистент",
    description="API за аптечен чатбот - препоръки за продукти без рецепта на български език",
    version="1.0.0",
)

# CORS for Open WebUI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Endpoints
# =============================================================================


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "ViaPharma Аптечен Асистент",
        "description": MODEL_DESCRIPTION,
        "language": "bg"
    }


@app.get("/hints")
async def get_hints():
    """
    Get suggested medical queries in Bulgarian.

    These hints can be displayed in the UI to help users know what to ask.
    """
    return {
        "hints": MODEL_HINTS,
        "placeholder": "Опишете вашите симптоми...",
        "welcome_message": "Здравейте! Аз съм вашият аптечен асистент. Как мога да ви помогна днес?",
        "examples_title": "Примерни въпроси:",
    }


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
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completions endpoint.

    Processes messages through the ViaPharma pipeline and returns
    a response in OpenAI's format.
    """
    # Extract the last user message
    user_message = None
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content
            break

    if not user_message:
        raise HTTPException(status_code=400, detail="Няма съобщение от потребителя")

    # Handle streaming (simplified - just returns full response)
    if request.stream:
        return await _stream_response(user_message, request.model)

    # Process through pipeline
    pipeline = get_pipeline()
    result = pipeline.process(user_message)

    # Build response
    response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

    # Estimate token counts (rough approximation)
    prompt_tokens = sum(len(m.content.split()) * 2 for m in request.messages)
    completion_tokens = len(result.response.split()) * 2

    return ChatCompletionResponse(
        id=response_id,
        created=created,
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


async def _stream_response(user_message: str, model: str):
    """
    Stream response in SSE format (OpenAI streaming format).

    Note: This is a simplified implementation that generates the full
    response first, then streams it in chunks.
    """
    import json

    async def generate():
        # Process through pipeline
        pipeline = get_pipeline()
        result = pipeline.process(user_message)

        response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        created = int(time.time())

        # Stream the response in chunks
        words = result.response.split(" ")
        for i, word in enumerate(words):
            chunk_content = word + (" " if i < len(words) - 1 else "")

            chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk_content},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        # Send final chunk with finish_reason
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

    print("=" * 60)
    print("🏥 ViaPharma Аптечен Асистент - API Сървър")
    print("=" * 60)
    print("\nOpenAI-съвместими endpoints:")
    print("  - GET  /v1/models        (списък модели)")
    print("  - POST /v1/chat/completions (чат)")
    print("  - GET  /hints            (примерни въпроси)")
    print("\n📡 Свържете Open WebUI към: http://localhost:8000/v1")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000)
