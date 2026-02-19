"""
Test builders for creating test data following contracts.

These builders make it easy to create valid test data that satisfies contracts.
"""

from src.medical_model import MedicalReasoning
from src.common.models import Product


class MedicalReasoningBuilder:
    """
    Builder for creating MedicalReasoning objects in tests.

    Example:
        >>> reasoning = (MedicalReasoningBuilder()
        ...     .with_symptoms(["headache", "fever"])
        ...     .with_treatment_type("analgesics")
        ...     .build())
    """

    def __init__(self):
        self._symptoms = []
        self._likely_cause = ""
        self._treatment_type = ""
        self._warnings = []
        self._see_doctor = False
        self._user_conditions = []
        self._explanation = ""
        self._how_treatment_helps = ""
        self._self_care_tips = []
        self._duration_guidance = ""

    def with_symptoms(self, symptoms: list[str]) -> "MedicalReasoningBuilder":
        """Add symptoms to the reasoning."""
        self._symptoms = symptoms
        return self

    def with_likely_cause(self, cause: str) -> "MedicalReasoningBuilder":
        """Set the likely cause."""
        self._likely_cause = cause
        return self

    def with_treatment_type(self, treatment_type: str) -> "MedicalReasoningBuilder":
        """Set the treatment type."""
        self._treatment_type = treatment_type
        return self

    def with_warnings(self, warnings: list[str]) -> "MedicalReasoningBuilder":
        """Add warnings."""
        self._warnings = warnings
        return self

    def with_see_doctor(self, see_doctor: bool = True) -> "MedicalReasoningBuilder":
        """Set whether to see doctor."""
        self._see_doctor = see_doctor
        return self

    def with_user_conditions(self, conditions: list[str]) -> "MedicalReasoningBuilder":
        """Add user conditions (pregnancy, allergies, etc.)."""
        self._user_conditions = conditions
        return self

    def with_explanation(self, explanation: str) -> "MedicalReasoningBuilder":
        """Add detailed explanation."""
        self._explanation = explanation
        return self

    def build(self) -> MedicalReasoning:
        """Build the MedicalReasoning object."""
        return MedicalReasoning(
            symptoms=self._symptoms,
            likely_cause=self._likely_cause,
            treatment_type=self._treatment_type,
            warnings=self._warnings,
            see_doctor=self._see_doctor,
            user_conditions=self._user_conditions,
            explanation=self._explanation,
            how_treatment_helps=self._how_treatment_helps,
            self_care_tips=self._self_care_tips,
            duration_guidance=self._duration_guidance,
        )


class ProductBuilder:
    """
    Builder for creating Product objects in tests.

    Example:
        >>> product = (ProductBuilder()
        ...     .with_id("1")
        ...     .with_title("Paracetamol 500mg")
        ...     .with_price(5.00, 2.50)
        ...     .build())
    """

    def __init__(self):
        self._id = ""
        self._title = ""
        self._brand = ""
        self._manufacturer = ""
        self._category = ""
        self._tags = ""
        self._url_handle = ""
        self._price_bgn = 0.0
        self._price_eur = 0.0
        self._description = ""
        self._composition = ""
        self._usage = ""
        self._contraindications = ""
        self._barcode = ""
        self._image_url = ""
        self._target_audience = ""
        self._form = ""
        self._is_otc = True
        self._score = 0.0

    def with_id(self, id: str) -> "ProductBuilder":
        """Set product ID."""
        self._id = id
        return self

    def with_title(self, title: str) -> "ProductBuilder":
        """Set product title."""
        self._title = title
        return self

    def with_brand(self, brand: str) -> "ProductBuilder":
        """Set product brand."""
        self._brand = brand
        return self

    def with_price(self, bgn: float, eur: float = None) -> "ProductBuilder":
        """Set product price."""
        self._price_bgn = bgn
        self._price_eur = eur if eur is not None else bgn / 2.0
        return self

    def with_description(self, description: str) -> "ProductBuilder":
        """Set product description."""
        self._description = description
        return self

    def with_composition(self, composition: str) -> "ProductBuilder":
        """Set product composition."""
        self._composition = composition
        return self

    def with_contraindications(self, contraindications: str) -> "ProductBuilder":
        """Set contraindications."""
        self._contraindications = contraindications
        return self

    def with_target_audience(self, audience: str) -> "ProductBuilder":
        """Set target audience (e.g., 'children', 'adults')."""
        self._target_audience = audience
        return self

    def for_children(self) -> "ProductBuilder":
        """Make this a child-appropriate product."""
        self._target_audience = "children"
        if "child" not in self._description.lower():
            self._description = f"For children. {self._description}"
        return self

    def for_adults_only(self) -> "ProductBuilder":
        """Make this an adult-only product."""
        self._target_audience = "adults"
        if "adult" not in self._description.lower():
            self._description = f"For adults only. {self._description}"
        return self

    def as_homeopathic(self) -> "ProductBuilder":
        """Make this a homeopathic product."""
        if "homeo" not in self._description.lower():
            self._description = f"Homeopathic. {self._description}"
        return self

    def build(self) -> Product:
        """Build the Product object."""
        return Product(
            id=self._id,
            title=self._title,
            brand=self._brand,
            manufacturer=self._manufacturer,
            category=self._category,
            tags=self._tags,
            url_handle=self._url_handle,
            price_bgn=self._price_bgn,
            price_eur=self._price_eur,
            description=self._description,
            composition=self._composition,
            usage=self._usage,
            contraindications=self._contraindications,
            barcode=self._barcode,
            image_url=self._image_url,
            target_audience=self._target_audience,
            form=self._form,
            is_otc=self._is_otc,
            score=self._score,
        )


# Convenience functions for common test data patterns

def simple_medical_reasoning(symptom: str, treatment: str = "analgesics") -> MedicalReasoning:
    """Create simple medical reasoning with one symptom."""
    return (MedicalReasoningBuilder()
            .with_symptoms([symptom])
            .with_likely_cause(f"{symptom}")
            .with_treatment_type(treatment)
            .build())


def complex_medical_reasoning(symptoms: list[str], treatment: str, see_doctor: bool = False) -> MedicalReasoning:
    """Create complex medical reasoning with multiple symptoms."""
    return (MedicalReasoningBuilder()
            .with_symptoms(symptoms)
            .with_likely_cause(f"Multiple symptoms: {', '.join(symptoms)}")
            .with_treatment_type(treatment)
            .with_see_doctor(see_doctor)
            .with_warnings(["Monitor symptoms"] if see_doctor else [])
            .build())


def simple_product(id: str, title: str, price: float = 10.0) -> Product:
    """Create simple product with minimal data."""
    return (ProductBuilder()
            .with_id(id)
            .with_title(title)
            .with_price(price)
            .build())


def child_product(id: str, title: str, price: float = 10.0) -> Product:
    """Create child-appropriate product."""
    return (ProductBuilder()
            .with_id(id)
            .with_title(title)
            .with_price(price)
            .for_children()
            .build())


def adult_product(id: str, title: str, price: float = 10.0) -> Product:
    """Create adult-only product."""
    return (ProductBuilder()
            .with_id(id)
            .with_title(title)
            .with_price(price)
            .for_adults_only()
            .build())


def product_list(*products: Product) -> list[Product]:
    """Create a list of products."""
    return list(products)
