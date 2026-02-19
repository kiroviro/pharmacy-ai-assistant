"""
E2E regression tests to catch integration bugs that unit tests miss.

These tests use the REAL pipeline with REAL dependencies (no mocks) to verify
that the entire system works end-to-end.

CRITICAL: Run these tests before every deployment to catch regressions.
"""

import pytest

from src.pipeline.orchestrator import Pipeline


class TestE2ERegressions:
    """End-to-end regression tests that would have caught the text validation bug."""

    @pytest.fixture
    def pipeline(self):
        """Create a real Pipeline instance (no mocks)."""
        return Pipeline()

    def test_response_has_all_required_sections(self, pipeline):
        """
        REGRESSION TEST: Verify response contains all required markdown sections.

        This test would have caught the text_validator.filter_garbage_sentences()
        bug that was destroying 77% of the response content.

        Bug history:
        - Response builder created 2,748 char response with all sections ✅
        - text_validator destroyed it to 627 chars, removing sections ❌
        - Unit tests passed because they used mocks
        """
        # Test with a common headache query (Bulgarian)
        result = pipeline.process("боли ме главата")
        response = result.response

        # Verify response is substantial (not truncated)
        assert len(response) > 1000, f"Response too short ({len(response)} chars) - likely truncated"

        # Verify all required sections are present
        required_sections = {
            "🔍": "Information/header section",
            "💊": "Ingredients section",
            "🛒": "Products section",
            "⚠️": "Triage/warning section",
            "ℹ️": "Footer/disclaimer section",
        }

        for emoji, description in required_sections.items():
            assert emoji in response, (
                f"Missing {description} ({emoji})\n"
                f"Response length: {len(response)} chars\n"
                f"First 500 chars: {response[:500]}"
            )

        # Verify structured markdown sections exist
        assert "##" in response, "No markdown headers found - response not properly formatted"
        assert "---" in response, "No section separators found - response not properly formatted"

    def test_products_are_returned_for_common_symptoms(self, pipeline):
        """
        REGRESSION TEST: Verify products are actually returned for common queries.

        This catches the Product.__init__() bug where database fields (status, sku)
        caused all products to fail conversion, returning 0 products.
        """
        common_queries = [
            "боли ме главата",  # headache
            "имам температура",  # fever
            "кашлица",  # cough
        ]

        for query in common_queries:
            result = pipeline.process(query)

            # Should return products
            assert result.products is not None, f"No products returned for '{query}'"
            assert len(result.products) > 0, f"Empty products list for '{query}'"

            # Products should appear in response
            assert "🛒" in result.response, f"Products section missing for '{query}'"

    def test_response_is_not_truncated_by_timeout(self, pipeline):
        """
        REGRESSION TEST: Verify responses complete within timeout.

        Catches the timeout bug where 20s limit was too short for 13-18s processing,
        causing incomplete responses.
        """
        result = pipeline.process("боли ме главата")

        # Processing should complete (not timeout)
        assert result.processing_time_ms > 0, "Processing time not recorded"
        assert result.processing_time_ms < 60000, "Processing took too long (>60s)"

        # Response should be complete (not cut off mid-sentence)
        assert result.response.endswith((".", "листовката.", "фармацевт.")), (
            "Response appears truncated (doesn't end with proper sentence)"
        )

    def test_response_quality_metrics(self, pipeline):
        """
        REGRESSION TEST: Verify response meets quality standards.

        Catches formatting issues, encoding problems, or garbled text.
        """
        result = pipeline.process("боли ме главата")
        response = result.response

        # Check Bulgarian content ratio
        bulgarian_chars = set("абвгдежзийклмнопрстуфхцчшщъьюя")
        cyrillic_count = sum(1 for c in response.lower() if c in bulgarian_chars)
        alpha_count = sum(1 for c in response if c.isalpha())

        if alpha_count > 0:
            bulgarian_ratio = cyrillic_count / alpha_count
            assert bulgarian_ratio > 0.8, (
                f"Response has too little Bulgarian content ({bulgarian_ratio:.1%})\n"
                "Possible translation failure or encoding issue"
            )

        # Check for common formatting issues
        assert not response.startswith(" "), "Response has leading whitespace"
        assert "\n\n\n\n" not in response, "Excessive blank lines in response"
        assert "  " not in response or response.count("  ") < 5, "Excessive double spaces"


class TestE2EPerformance:
    """Performance regression tests."""

    @pytest.fixture
    def pipeline(self):
        return Pipeline(use_unified_processor=True)

    def test_processing_time_within_acceptable_range(self, pipeline):
        """Verify processing doesn't regress significantly."""
        result = pipeline.process("боли ме главата")

        # Should complete within reasonable time
        # (adjust based on your hardware/model speed)
        assert result.processing_time_ms < 30000, (
            f"Processing too slow: {result.processing_time_ms}ms\n"
            "Possible performance regression"
        )


@pytest.mark.skip(reason="Requires running API server - use for smoke tests before deployment")
class TestE2EAPISmoke:
    """
    Smoke tests for deployed API.

    Run these against localhost:8000 or staging before deploying to production.
    """

    def test_api_returns_complete_response(self):
        """Verify API returns complete, well-formatted responses."""
        import requests

        response = requests.post(
            "http://localhost:8000/v1/chat/completions",
            json={
                "model": "viapharma-assistant",
                "messages": [{"role": "user", "content": "боли ме главата"}]
            },
            timeout=90
        )

        assert response.status_code == 200, f"API returned {response.status_code}"

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        # Same checks as unit tests
        assert len(content) > 1000, "API response too short"
        assert "💊" in content, "Missing ingredients section"
        assert "🛒" in content, "Missing products section"
        assert "⚠️" in content, "Missing triage section"
