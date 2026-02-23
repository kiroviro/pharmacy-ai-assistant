"""
Test that active ingredients section is always shown when products exist.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.common.models import Product
from src.pipeline.orchestrator import Pipeline
from src.unified_processor import (
    ExtractionResult,
    IntentResult,
    ReasoningResult,
    SafetyResult,
    UnifiedProcessorResult,
)


def test_ingredients_section_always_shown():
    """Test that active ingredients section appears even when extraction fails."""
    pipeline = Pipeline()

    mock_products = [
        Product(
            id="dialgin-001",
            title="Диалгин",
            category="Болкоуспокояващи",
            description="За температура и болка",
            composition="Парацетамол",
            image_url="",
        ),
        Product(
            id="nurofen-001",
            title="Нурофен",
            category="Болкоуспокояващи",
            description="За възпаление и болка",
            composition="Ибупрофен",
            image_url="",
        ),
    ]

    mock_llm_result = UnifiedProcessorResult(
        intent=IntentResult(is_pharmacy_related=True, confidence=0.95),
        safety=SafetyResult(level="safe", action="proceed"),
        reasoning=ReasoningResult(
            treatment_category="",  # Empty - should trigger fallback
            explanation="Температурата е симптом на инфекция.",
            explanation_bg="Температурата е симптом на инфекция.",
            self_care_tips=["Пийте течности"],
            self_care_tips_bg=["Пийте течности"],
            warnings=["Потърсете лекар ако..."],
            warnings_bg=["Потърсете лекар ако..."],
        ),
        extraction=ExtractionResult(
            symptoms=["fever"], user_conditions=[], age_group="adult", query_translated="I have a fever"
        ),
    )

    response = pipeline._format_response_from_unified(
        llm_result=mock_llm_result, products=mock_products, original_query="Имам температура"
    )

    assert "## 💊 Подходящи активни съставки" in response
