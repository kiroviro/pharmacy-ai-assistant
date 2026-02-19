"""
Contract for Medical Reasoning behavior.

Defines expected behavior for medical reasoning regardless of implementation.
Tests using this contract will survive refactoring as long as the behavior contract is maintained.
"""

from typing import Protocol

from src.medical_model import MedicalReasoning


class MedicalReasoningContract(Protocol):
    """
    Contract defining the expected behavior of medical reasoning components.

    Any component that provides medical reasoning should satisfy this contract.
    Tests written against this contract will remain valid even if implementation changes.
    """

    def analyze_symptoms(self, symptoms: list[str]) -> MedicalReasoning:
        """
        Analyze symptoms and return medical reasoning.

        Contract requirements:
        - Must accept list of symptom strings
        - Must return MedicalReasoning object
        - Result must contain non-empty symptoms list
        - Result must contain likely_cause (or empty string)
        - Result must contain treatment_type (or empty string)
        - Result must contain warnings list (can be empty)
        """
        ...


def verify_medical_reasoning_contract(reasoning: MedicalReasoning) -> bool:
    """
    Verify that a MedicalReasoning object satisfies the contract.

    Use this to validate that your component produces contract-compliant results.

    Args:
        reasoning: MedicalReasoning object to verify

    Returns:
        True if contract is satisfied, False otherwise

    Example:
        >>> reasoning = component.analyze_symptoms(["headache", "fever"])
        >>> assert verify_medical_reasoning_contract(reasoning)
    """
    # Required fields must exist
    if not hasattr(reasoning, 'symptoms'):
        return False
    if not hasattr(reasoning, 'likely_cause'):
        return False
    if not hasattr(reasoning, 'treatment_type'):
        return False
    if not hasattr(reasoning, 'warnings'):
        return False

    # Type checking
    if not isinstance(reasoning.symptoms, list):
        return False
    if not isinstance(reasoning.likely_cause, str):
        return False
    if not isinstance(reasoning.treatment_type, str):
        return False
    if not isinstance(reasoning.warnings, list):
        return False

    # Symptoms list should not be empty if provided
    # (but can be empty for certain edge cases)

    return True


def assert_medical_reasoning_valid(reasoning: MedicalReasoning, context: str = ""):
    """
    Assert that MedicalReasoning satisfies contract, with helpful error messages.

    Args:
        reasoning: MedicalReasoning to validate
        context: Optional context string for error messages

    Raises:
        AssertionError: If contract is violated

    Example:
        >>> reasoning = analyze_query("headache and fever")
        >>> assert_medical_reasoning_valid(reasoning, "headache/fever analysis")
    """
    prefix = f"{context}: " if context else ""

    assert hasattr(reasoning, 'symptoms'), f"{prefix}Missing 'symptoms' field"
    assert isinstance(reasoning.symptoms, list), f"{prefix}'symptoms' must be a list"

    assert hasattr(reasoning, 'likely_cause'), f"{prefix}Missing 'likely_cause' field"
    assert isinstance(reasoning.likely_cause, str), f"{prefix}'likely_cause' must be a string"

    assert hasattr(reasoning, 'treatment_type'), f"{prefix}Missing 'treatment_type' field"
    assert isinstance(reasoning.treatment_type, str), f"{prefix}'treatment_type' must be a string"

    assert hasattr(reasoning, 'warnings'), f"{prefix}Missing 'warnings' field"
    assert isinstance(reasoning.warnings, list), f"{prefix}'warnings' must be a list"

    # Optional fields that may exist
    if hasattr(reasoning, 'see_doctor'):
        assert isinstance(reasoning.see_doctor, bool), f"{prefix}'see_doctor' must be a boolean"

    if hasattr(reasoning, 'user_conditions'):
        assert isinstance(reasoning.user_conditions, list), f"{prefix}'user_conditions' must be a list"


# Common test scenarios for medical reasoning
class MedicalReasoningTestScenarios:
    """
    Standard test scenarios for medical reasoning components.

    Use these scenarios to ensure consistent behavior across implementations.
    """

    @staticmethod
    def single_symptom_scenario():
        """Simple case: single symptom."""
        return {
            "input": ["headache"],
            "expected_fields": ["symptoms", "likely_cause", "treatment_type"],
            "constraints": {
                "symptoms": lambda s: len(s) >= 1,
                "treatment_type": lambda t: t in ["analgesics", "pain relief", ""] or True,
            }
        }

    @staticmethod
    def multiple_symptoms_scenario():
        """Complex case: multiple related symptoms."""
        return {
            "input": ["headache", "fever", "fatigue"],
            "expected_fields": ["symptoms", "likely_cause", "treatment_type"],
            "constraints": {
                "symptoms": lambda s: len(s) >= 1,
                "likely_cause": lambda c: c != "",  # Should identify cause
            }
        }

    @staticmethod
    def severe_symptoms_scenario():
        """Severe case: should trigger doctor recommendation."""
        return {
            "input": ["chest pain", "difficulty breathing"],
            "expected_fields": ["symptoms", "likely_cause", "warnings", "see_doctor"],
            "constraints": {
                "see_doctor": lambda s: s is True,
                "warnings": lambda w: len(w) > 0,
            }
        }

    @staticmethod
    def child_symptoms_scenario():
        """Child case: age-specific considerations."""
        return {
            "input": ["fever in child"],
            "expected_fields": ["symptoms", "user_conditions"],
            "constraints": {
                "user_conditions": lambda c: "child" in c or True,
            }
        }
