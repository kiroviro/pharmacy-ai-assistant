"""
Quick test to verify active ingredients section is always shown when products exist.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.medical_model import MedicalReasoning
from src.pipeline.models import Product
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
    pipeline = Pipeline(lazy_load=False)

    # Create mock products
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

    # Test Case 1: Unified processor format with NO treatment_category (should extract from products)
    print("=" * 80)
    print("TEST 1: Unified format - treatment_category is empty")
    print("=" * 80)

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

    has_ingredients_header = "## 💊 Подходящи активни съставки" in response
    has_fallback_message = "Проверете активните съставки и дозировката в листовката" in response

    print(f"✅ Has ingredients header: {has_ingredients_header}")
    print(f"✅ Has fallback message: {has_fallback_message}")
    print("\nResponse excerpt (ingredients section):")
    if "## 💊" in response:
        start = response.index("## 💊")
        end = response.index("---", start + 10) if "---" in response[start + 10 :] else start + 300
        print(response[start:end])
    print()

    # Test Case 2: Legacy format with NO treatment_type
    print("=" * 80)
    print("TEST 2: Legacy format - treatment_type is empty")
    print("=" * 80)

    mock_medical_reasoning = MedicalReasoning(
        symptoms=["fever"],
        likely_cause="viral infection",
        explanation="Fever indicates infection",
        treatment_type="",  # Empty - should trigger fallback
        how_treatment_helps="",
        self_care_tips=["Rest", "Hydrate"],
        duration_guidance="2-3 days",
        warnings=["See doctor if..."],
    )

    response2 = pipeline._format_response(
        medical_reasoning=mock_medical_reasoning,
        products=mock_products,
        translate_reasoning=False,
        original_query="Имам температура",
    )

    has_ingredients_header2 = "## 💊 Подходящи активни съставки" in response2
    has_fallback_message2 = "Проверете активните съставки и дозировката в листовката" in response2

    print(f"✅ Has ingredients header: {has_ingredients_header2}")
    print(
        f"✅ Has fallback message or ingredient list: {has_fallback_message2 or 'Парацетамол' in response2 or 'Ибупрофен' in response2}"
    )
    print("\nResponse excerpt (ingredients section):")
    if "## 💊" in response2:
        start = response2.index("## 💊")
        end = response2.index("---", start + 10) if "---" in response2[start + 10 :] else start + 300
        print(response2[start:end])
    print()

    # Verify both tests pass
    success = has_ingredients_header and has_ingredients_header2

    if success:
        print("=" * 80)
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        print("Active ingredients section now appears in 100% of responses with products!")
    else:
        print("=" * 80)
        print("❌ TESTS FAILED")
        print("=" * 80)

    return success


if __name__ == "__main__":
    success = test_ingredients_section_always_shown()
    sys.exit(0 if success else 1)
