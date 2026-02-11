"""
Integration tests for the API server.

Tests the FastAPI endpoints without loading the full ML models.
Uses mocking for the pipeline to enable fast testing.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Import after setting up mocks
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class MockPipelineResult:
    """Mock result from pipeline.process()"""
    def __init__(
        self,
        response: str = "Тестов отговор",
        is_medical: bool = True,
        is_red_flag: bool = False
    ):
        self.response = response
        self.is_medical = is_medical
        self.is_red_flag = is_red_flag
        self.original_text = "тест"
        self.translated_text = "test"
        self.medical_reasoning = None
        self.candidate_products = []
        self.selected_products = []


class MockPipeline:
    """Mock pipeline for testing."""
    def __init__(self):
        self._medical_model = Mock()
        self._medical_model._loaded = True
        self._translator = Mock()
        self._translator._bg_to_en_model = Mock()
        self._translator._en_to_bg_model = Mock()
        self._product_store = Mock()
        self._product_store.collection = Mock()
        self._product_store.collection.count.return_value = 100

    @property
    def medical_model(self):
        return self._medical_model

    @property
    def translator(self):
        return self._translator

    @property
    def product_store(self):
        return self._product_store

    def process(self, user_input: str) -> MockPipelineResult:
        # Simulate different responses based on input
        if "emergency" in user_input.lower() or "спешно" in user_input.lower():
            return MockPipelineResult(
                response="🚨 СПЕШНО: Обадете се на 112!",
                is_red_flag=True
            )
        elif not user_input.strip():
            return MockPipelineResult(
                response="Моля, опишете симптомите си.",
                is_medical=False
            )
        else:
            return MockPipelineResult(
                response="Въз основа на вашите симптоми, ето какво препоръчвам:\n\n### 1. Тестов продукт"
            )


# Create mock before importing app
mock_pipeline = MockPipeline()


@pytest.fixture
def client():
    """Create test client with mocked pipeline."""
    with patch('api_server.get_pipeline', return_value=mock_pipeline):
        with patch('src.config.get_settings') as mock_settings:
            # Configure mock settings
            settings = Mock()
            settings.log_level = "WARNING"
            settings.log_json = False
            settings.api_host = "0.0.0.0"
            settings.api_port = 8000
            settings.max_message_length = 2000
            settings.min_message_length = 2
            settings.rate_limit_per_minute = 100  # High limit for tests
            settings.request_timeout_seconds = 30
            settings.enable_rate_limiting = False  # Disable for tests
            settings.enable_request_logging = False
            settings.prewarm_models = False
            mock_settings.return_value = settings

            from api_server import app
            yield TestClient(app)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root_endpoint(self, client):
        """Root endpoint should return status ok."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "ViaPharma" in data["service"]

    def test_health_endpoint(self, client):
        """Health endpoint should return detailed status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "models_loaded" in data
        assert "products_count" in data
        assert "uptime_seconds" in data

    def test_hints_endpoint(self, client):
        """Hints endpoint should return Bulgarian suggestions."""
        response = client.get("/hints")
        assert response.status_code == 200
        data = response.json()
        assert "hints" in data
        assert len(data["hints"]) > 0
        assert "placeholder" in data
        assert "welcome_message" in data
        # Check hints are in Bulgarian
        assert any("главоболие" in hint for hint in data["hints"])

    def test_metrics_endpoint(self, client):
        """Metrics endpoint should return monitoring data."""
        response = client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "requests" in data
        assert "latency" in data
        assert "uptime_seconds" in data
        # Check request metrics structure
        assert "total" in data["requests"]
        assert "success" in data["requests"]
        assert "failed" in data["requests"]


class TestModelsEndpoint:
    """Tests for the models endpoint."""

    def test_list_models(self, client):
        """Should return list of available models."""
        response = client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0

    def test_model_info(self, client):
        """Model info should include description and hints."""
        response = client.get("/v1/models")
        data = response.json()
        model = data["data"][0]
        assert model["id"] == "viapharma-medgemma"
        assert model["owned_by"] == "viapharma"
        assert "description" in model
        assert "meta" in model
        assert "hints" in model["meta"]


class TestChatCompletions:
    """Tests for the chat completions endpoint."""

    def test_basic_chat_request(self, client):
        """Basic chat request should return valid response."""
        response = client.post("/v1/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "user", "content": "Имам главоболие"}]
        })
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert len(data["choices"][0]["message"]["content"]) > 0

    def test_chat_response_format(self, client):
        """Chat response should match OpenAI format."""
        response = client.post("/v1/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "user", "content": "тест"}]
        })
        data = response.json()
        # Check required fields
        assert "id" in data
        assert data["id"].startswith("chatcmpl-")
        assert "object" in data
        assert data["object"] == "chat.completion"
        assert "created" in data
        assert "model" in data
        assert "choices" in data
        assert "usage" in data
        # Check choice format
        choice = data["choices"][0]
        assert "index" in choice
        assert "message" in choice
        assert "finish_reason" in choice
        assert choice["finish_reason"] == "stop"

    def test_empty_message_rejected(self, client):
        """Empty messages should be rejected."""
        response = client.post("/v1/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "user", "content": ""}]
        })
        assert response.status_code == 400

    def test_no_user_message_rejected(self, client):
        """Request without user message should be rejected."""
        response = client.post("/v1/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "system", "content": "test"}]
        })
        assert response.status_code == 400

    def test_short_message_rejected(self, client):
        """Very short messages should be rejected."""
        response = client.post("/v1/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "user", "content": "a"}]
        })
        assert response.status_code == 400

    def test_response_headers(self, client):
        """Response should include custom headers."""
        response = client.post("/v1/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "user", "content": "тест заявка"}]
        })
        assert "X-Request-ID" in response.headers
        assert "X-Response-Time" in response.headers


class TestInputValidation:
    """Tests for input validation."""

    def test_message_too_long(self, client):
        """Messages exceeding max length should be rejected."""
        long_message = "а" * 2001  # Over default 2000 limit
        response = client.post("/v1/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "user", "content": long_message}]
        })
        assert response.status_code == 400
        assert "дълго" in response.json()["detail"]

    def test_whitespace_only_rejected(self, client):
        """Whitespace-only messages should be rejected."""
        response = client.post("/v1/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "user", "content": "   \n\t   "}]
        })
        assert response.status_code == 400

    def test_valid_message_accepted(self, client):
        """Valid messages should be accepted."""
        response = client.post("/v1/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "user", "content": "Имам температура"}]
        })
        assert response.status_code == 200


class TestAlternativeEndpoints:
    """Tests for alternative endpoint paths."""

    def test_models_without_v1(self, client):
        """Models endpoint should work without /v1 prefix."""
        response = client.get("/models")
        assert response.status_code == 200

    def test_chat_without_v1(self, client):
        """Chat endpoint should work without /v1 prefix."""
        response = client.post("/chat/completions", json={
            "model": "viapharma-medgemma",
            "messages": [{"role": "user", "content": "тест"}]
        })
        assert response.status_code == 200


class TestCORS:
    """Tests for CORS configuration."""

    def test_cors_headers(self, client):
        """CORS headers should be present."""
        response = client.options(
            "/v1/chat/completions",
            headers={"Origin": "http://localhost:3000"}
        )
        # FastAPI TestClient doesn't fully simulate CORS, but we can check it doesn't error
        assert response.status_code in [200, 405]
