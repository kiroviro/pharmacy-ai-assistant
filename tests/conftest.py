"""
Pytest configuration and fixtures for ViaPharma tests.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Mock MLX for CI environments (MLX only works on Apple Silicon)
# This allows tests to import modules that use MLX without having the package installed
try:
    import mlx.core  # noqa: F401
except (ImportError, ModuleNotFoundError):
    # Create proper mock modules for MLX with __spec__ set
    # This is required for importlib.util.find_spec() to work (used by transformers)
    from importlib.machinery import ModuleSpec

    mlx_mock = MagicMock()
    mlx_mock.__spec__ = ModuleSpec("mlx", None)
    mlx_mock.__version__ = "0.0.0"

    mlx_core_mock = MagicMock()
    mlx_core_mock.__spec__ = ModuleSpec("mlx.core", None)

    mlx_nn_mock = MagicMock()
    mlx_nn_mock.__spec__ = ModuleSpec("mlx.nn", None)

    mlx_lm_mock = MagicMock()
    mlx_lm_mock.__spec__ = ModuleSpec("mlx_lm", None)
    mlx_lm_mock.generate = MagicMock(return_value=("", 0))
    mlx_lm_mock.load = MagicMock(return_value=(MagicMock(), MagicMock()))

    mlx_lm_sample_utils_mock = MagicMock()
    mlx_lm_sample_utils_mock.__spec__ = ModuleSpec("mlx_lm.sample_utils", None)
    mlx_lm_sample_utils_mock.make_sampler = MagicMock(return_value=MagicMock())

    mlx_lm_utils_mock = MagicMock()
    mlx_lm_utils_mock.__spec__ = ModuleSpec("mlx_lm.utils", None)

    sys.modules["mlx"] = mlx_mock
    sys.modules["mlx.core"] = mlx_core_mock
    sys.modules["mlx.nn"] = mlx_nn_mock
    sys.modules["mlx_lm"] = mlx_lm_mock
    sys.modules["mlx_lm.sample_utils"] = mlx_lm_sample_utils_mock
    sys.modules["mlx_lm.utils"] = mlx_lm_utils_mock

from src.safety import SafetyLayer  # noqa: E402
from src.unified_processor import (  # noqa: E402
    ProcessorCache,
)


@pytest.fixture
def safety_layer():
    """Create a fresh SafetyLayer instance for testing."""
    return SafetyLayer()


@pytest.fixture
def processor_cache():
    """Create a fresh ProcessorCache instance for testing."""
    return ProcessorCache(max_size=100)


# =============================================================================
# Test Data: Emergency Symptoms (Must detect 100%)
# =============================================================================


@pytest.fixture
def emergency_symptoms_bg():
    """Bulgarian emergency symptoms that MUST be detected."""
    return [
        "не мога да дишам",
        "задушавам се",
        "болка в гърдите",
        "силна болка в гърдите",
        "стягане в гърдите",
        "загуба на съзнание",
        "припаднах",
        "не мога да говоря",
        "парализа",
        "гърч",
        "гърчове",
        "силно кървене",
        "отравяне",
        "суицидни мисли",
        "искам да се убия",
    ]


@pytest.fixture
def emergency_symptoms_en():
    """English emergency symptoms that MUST be detected."""
    return [
        "can't breathe",
        "difficulty breathing",
        "chest pain",
        "chest pressure",
        "loss of consciousness",
        "fainted",
        "can't speak",
        "paralysis",
        "seizure",
        "severe bleeding",
        "poisoning",
        "suicidal",
        "want to kill myself",
    ]


# =============================================================================
# Test Data: Urgent Symptoms
# =============================================================================


@pytest.fixture
def urgent_symptoms_bg():
    """Bulgarian urgent symptoms."""
    return [
        "кръв в урината",
        "кръв в изпражненията",
        "повръщане на кръв",
        "силна коремна болка",
        "висока температура над 39",
        "най-силното главоболие",
        "схванат врат",
        "жълти очи",
        "жълтеница",
        "не мога да уринирам",
    ]


@pytest.fixture
def urgent_symptoms_en():
    """English urgent symptoms."""
    return [
        "blood in urine",
        "blood in stool",
        "vomiting blood",
        "severe abdominal pain",
        "high fever over 39",
        "worst headache ever",
        "stiff neck",
        "yellow eyes",
        "jaundice",
        "can't urinate",
    ]


# =============================================================================
# Test Data: Normal Medical Queries (Should NOT trigger red flags)
# =============================================================================


@pytest.fixture
def normal_medical_queries_bg():
    """Normal Bulgarian medical queries that should NOT trigger safety flags."""
    return [
        "имам главоболие",
        "боли ме гърлото",
        "имам хрема",
        "кашлям от два дни",
        "имам температура",
        "боли ме коремът",
        "имам алергия",
        "не мога да спя",
        "имам болки в гърба",
        "сърби ме кожата",
        "имам обрив",
        "уморен съм",
    ]


@pytest.fixture
def normal_medical_queries_en():
    """Normal English medical queries that should NOT trigger safety flags."""
    return [
        "I have a headache",
        "my throat hurts",
        "I have a runny nose",
        "I've been coughing for two days",
        "I have a fever",
        "my stomach hurts",
        "I have allergies",
        "I can't sleep",
        "my back hurts",
        "my skin is itchy",
        "I have a rash",
        "I'm tired",
    ]


# =============================================================================
# Test Data: Non-Medical Queries (Should be rejected)
# =============================================================================


@pytest.fixture
def non_medical_queries_bg():
    """Non-medical Bulgarian queries that should be rejected."""
    return [
        "какво е времето",
        "разкажи ми виц",
        "как се готви баница",
        "какви са новините",
        "кога е мачът",
        "искам да резервирам хотел",
        "колко е часът",
    ]


@pytest.fixture
def non_medical_queries_en():
    """Non-medical English queries that should be rejected."""
    return [
        "what's the weather",
        "tell me a joke",
        "how to cook pasta",
        "what's in the news",
        "when is the game",
        "I want to book a hotel",
        "what time is it",
    ]


# =============================================================================
# Test Data: Profanity (Should be rejected)
# =============================================================================


@pytest.fixture
def profanity_queries():
    """Queries with profanity that should be rejected."""
    return [
        "fuck this",
        "this is bullshit",
        "ебати",
        "шибан",
    ]
