"""
Pipeline orchestrator for the ViaPharma OTC Chatbot.

Pipeline follows the Perplexity two-stage retrieval pattern:
1. Vector DB returns top-K candidates (fast, cheap)
2. LLM refines and picks best matches (accurate)
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from src.config import get_settings
from src.intent_classifier import get_intent_classifier
from src.logging_config import get_logger
from src.medical_model import MedicalReasoning, get_medical_model
from src.product_store import get_product_store
from src.safety import get_safety_layer
from src.translator import get_translator

logger = get_logger("viapharma.pipeline")


# =============================================================================
# USER CONDITION EXTRACTION PATTERNS
# =============================================================================
# Maps user mentions to standardized condition identifiers

USER_CONDITION_PATTERNS = {
    # Pregnancy
    "pregnancy": [
        "бременна", "бременност", "pregnant", "pregnancy",
        "чакам бебе", "очаквам бебе", "expecting",
    ],
    # Breastfeeding
    "breastfeeding": [
        "кърмя", "кърмене", "кърмеща", "breastfeeding", "nursing",
        "кърмачка", "lactating",
    ],
    # Children
    "child": [
        "дете", "деца", "детето", "бебе", "child", "children", "kid",
        "малък", "малка", "infant", "toddler", "pediatric",
        r"\b[1-9]\s*годин", r"\b[1-9]\s*месец", r"\b[1-9]\s*year",
    ],
    # Elderly
    "elderly": [
        "възрастен", "пенсионер", "elderly", "senior",
        r"\b[789]\d\s*годин", "над 65", "over 65",
    ],
    # Diabetes
    "diabetes": [
        "диабет", "диабетик", "diabetes", "diabetic",
        "кръвна захар", "blood sugar", "инсулин",
    ],
    # Heart conditions
    "heart": [
        "сърце", "сърдечен", "heart", "cardiac",
        "кръвно налягане", "blood pressure", "хипертония", "hypertension",
        "аритмия", "arrhythmia",
    ],
    # Kidney issues
    "kidney": [
        "бъбрек", "бъбречен", "kidney", "renal",
        "бъбречна недостатъчност", "kidney failure",
    ],
    # Liver issues
    "liver": [
        "черен дроб", "чернодробен", "liver", "hepatic",
        "хепатит", "hepatitis",
    ],
    # Allergies
    "allergy": [
        "алергия", "алергичен", "allergy", "allergic",
        "непоносимост", "intolerance",
    ],
    # Stomach/GI issues
    "stomach": [
        "стомах", "язва", "гастрит", "stomach", "ulcer", "gastritis",
        "стомашни проблеми", "киселини",
    ],
    # Asthma
    "asthma": [
        "астма", "asthma", "астматик",
    ],
}


# =============================================================================
# CONTRAINDICATION PATTERNS
# =============================================================================
# Maps conditions to contraindication keywords to look for in product data

CONTRAINDICATION_KEYWORDS = {
    "pregnancy": [
        # Bulgarian variations (all grammatical forms)
        "бременност", "бременни", "бременна", "бременността",
        "през бременност", "по време на бременност",
        "в бременност", "при бременност",
        # English
        "pregnant", "pregnancy",
    ],
    "breastfeeding": [
        # Bulgarian variations
        "кърмене", "кърменето", "кърмачки", "кърмещи", "кърмачка",
        "през кърмене", "по време на кърмене", "при кърмене",
        # English
        "breastfeeding", "lactation", "nursing",
    ],
    "child": [
        # Bulgarian - age restrictions
        "деца под", "деца до", "деца на възраст под",
        "не се препоръчва за деца", "не давайте на деца",
        "под 12 години", "под 6 години", "под 2 години",
        "на възраст под",
        # English
        "children under", "pediatric", "not for children",
    ],
    "elderly": [
        "възрастни хора", "пациенти в старческа възраст",
        "над 65", "elderly", "старческа възраст",
    ],
    "diabetes": [
        "диабет", "диабетици", "захарен диабет",
        "diabetes", "diabetic", "кръвна захар",
    ],
    "heart": [
        "сърдечна недостатъчност", "сърдечни заболявания",
        "сърдечно-съдови", "сърдечен",
        "heart disease", "cardiac", "cardiovascular",
        "хипертония", "високо кръвно", "кръвно налягане",
    ],
    "kidney": [
        "бъбречна недостатъчност", "бъбречни заболявания",
        "бъбречна функция", "бъбречни проблеми",
        "kidney disease", "renal impairment", "renal failure",
    ],
    "liver": [
        "чернодробна недостатъчност", "чернодробни заболявания",
        "чернодробна функция", "чернодробни проблеми",
        "liver disease", "hepatic impairment", "hepatic failure",
    ],
    "allergy": [
        "свръхчувствителност", "алергия към", "алергични реакции",
        "алергични", "непоносимост",
        "hypersensitivity", "allergic to", "allergy",
    ],
    "stomach": [
        "стомашна язва", "пептична язва", "гастрит",
        "язви", "стомашни проблеми", "стомашно-чревни",
        "stomach ulcer", "peptic ulcer", "gastritis", "GI bleeding",
    ],
    "asthma": [
        "астма", "астматик", "бронхоспазъм", "бронхиална астма",
        "asthma", "bronchospasm", "asthmatic",
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def extract_user_conditions(text: str) -> list[str]:
    """
    Extract user conditions from query text (Bulgarian or English).

    Args:
        text: User query or translated text

    Returns:
        List of standardized condition identifiers
    """
    text_lower = text.lower()
    conditions = []

    for condition, patterns in USER_CONDITION_PATTERNS.items():
        for pattern in patterns:
            # Handle regex patterns (start with \b or contain special chars)
            if pattern.startswith(r"\b") or any(c in pattern for c in r"[]\d+*?"):
                if re.search(pattern, text_lower):
                    conditions.append(condition)
                    break
            else:
                if pattern in text_lower:
                    conditions.append(condition)
                    break

    if conditions:
        logger.info(f"Extracted user conditions: {conditions}")

    return conditions


def check_contraindication(product_contraindications: str, user_conditions: list[str]) -> tuple[bool, list[str]]:
    """
    Check if a product has contraindications matching user conditions.

    Args:
        product_contraindications: Product's contraindications text
        user_conditions: List of user condition identifiers

    Returns:
        Tuple of (has_contraindication, list of matching conditions)
    """
    if not product_contraindications or not user_conditions:
        return False, []

    contra_lower = product_contraindications.lower()
    matching_conditions = []

    for condition in user_conditions:
        keywords = CONTRAINDICATION_KEYWORDS.get(condition, [])
        for keyword in keywords:
            if keyword.lower() in contra_lower:
                matching_conditions.append(condition)
                break

    return len(matching_conditions) > 0, matching_conditions


def filter_by_contraindications(
    products: list,
    user_conditions: list[str],
    strict: bool = True
) -> tuple[list, list]:
    """
    Filter products that have contraindications matching user conditions.

    Args:
        products: List of Product objects
        user_conditions: List of user condition identifiers
        strict: If True, completely exclude contraindicated products
                If False, move them to end of list with warning

    Returns:
        Tuple of (safe_products, contraindicated_products)
    """
    if not user_conditions:
        return products, []

    safe_products = []
    contraindicated = []

    for product in products:
        has_contra, matching = check_contraindication(
            product.contraindications, user_conditions
        )

        if has_contra:
            logger.warning(
                f"Product '{product.title}' contraindicated for: {matching}",
                extra={"product_id": product.id, "conditions": matching}
            )
            contraindicated.append((product, matching))
        else:
            safe_products.append(product)

    logger.info(
        f"Contraindication filter: {len(safe_products)} safe, {len(contraindicated)} filtered",
        extra={"user_conditions": user_conditions}
    )

    return safe_products, contraindicated


def parse_composition_ingredients(composition: str) -> list[str]:
    """
    Parse active ingredients from composition text.

    Args:
        composition: Product composition text (Състав)

    Returns:
        List of identified active ingredient names
    """
    if not composition:
        return []

    # Common active ingredients with their patterns
    INGREDIENT_EXTRACTION = {
        "ibuprofen": [r"ибупрофен\s*[\d,]+\s*mg", r"ibuprofen\s*[\d,]+\s*mg"],
        "paracetamol": [r"парацетамол\s*[\d,]+\s*mg", r"paracetamol\s*[\d,]+\s*mg", r"acetaminophen"],
        "aspirin": [r"ацетилсалицилова\s+киселина", r"acetylsalicylic acid", r"аспирин"],
        "diclofenac": [r"диклофенак", r"diclofenac"],
        "naproxen": [r"напроксен", r"naproxen"],
        "loratadine": [r"лоратадин", r"loratadine"],
        "cetirizine": [r"цетиризин", r"cetirizine"],
        "pseudoephedrine": [r"псевдоефедрин", r"pseudoephedrine"],
        "dextromethorphan": [r"декстрометорфан", r"dextromethorphan"],
        "guaifenesin": [r"гвайфенезин", r"guaifenesin"],
        "codeine": [r"кодеин", r"codeine"],
        "caffeine": [r"кофеин", r"caffeine"],
        "vitamin_c": [r"витамин\s*c", r"аскорбинова\s+киселина", r"ascorbic acid"],
        "zinc": [r"цинк", r"zinc"],
        "ambroxol": [r"амброксол", r"ambroxol"],
        "bromhexine": [r"бромхексин", r"bromhexine"],
        "phenylephrine": [r"фенилефрин", r"phenylephrine"],
        "chlorpheniramine": [r"хлорфенирамин", r"chlorpheniramine"],
    }

    composition_lower = composition.lower()
    found = []

    for ingredient, patterns in INGREDIENT_EXTRACTION.items():
        for pattern in patterns:
            if re.search(pattern, composition_lower, re.IGNORECASE):
                found.append(ingredient)
                break

    return found


@dataclass
class Product:
    """Represents a product from the catalogue."""
    id: str
    title: str  # Product name
    brand: str = ""  # Марка
    manufacturer: str = ""  # Производител
    category: str = ""
    tags: str = ""
    url_handle: str = ""  # URL slug for product link

    # Pricing
    price_bgn: float = 0.0  # Price in лв
    price_eur: float = 0.0  # Price in €

    # Product details
    description: str = ""  # Описание
    composition: str = ""  # Състав
    usage: str = ""  # Начин на употреба
    contraindications: str = ""  # Противопоказания

    # Additional info
    barcode: str = ""
    image_url: str = ""
    target_audience: str = ""  # За кого
    form: str = ""  # Форма
    is_otc: bool = True

    # Search relevance
    score: float = 0.0

    @property
    def product_url(self) -> str:
        """Get the full URL to the product page."""
        if self.url_handle:
            base_url = get_settings().product_base_url
            return f"{base_url}/{self.url_handle}"
        return ""

    @classmethod
    def from_chromadb(cls, data: dict) -> "Product":
        """Create a Product from ChromaDB search result."""
        return cls(
            id=str(data.get("id", data.get("sku", ""))),
            title=data.get("title", ""),
            brand=data.get("brand", ""),
            manufacturer=data.get("manufacturer", ""),
            category=data.get("category", ""),
            tags=data.get("tags", ""),
            url_handle=data.get("url_handle", ""),
            price_bgn=float(data.get("price_bgn", 0)),
            price_eur=float(data.get("price_eur", 0)),
            description=data.get("description", ""),
            composition=data.get("composition", ""),
            usage=data.get("usage", ""),
            contraindications=data.get("contraindications", ""),
            barcode=data.get("barcode", ""),
            image_url=data.get("image_url", ""),
            target_audience=data.get("target_audience", ""),
            form=data.get("form", ""),
            is_otc=data.get("is_otc", True),
            score=float(data.get("score", 0)),
        )

    def to_display_string(self) -> str:
        """Format product for display in chat with clean markdown."""
        lines = []

        # Title - make it a link if URL available
        if self.product_url:
            lines.append(f"**[{self.title}]({self.product_url})**")
        else:
            lines.append(f"**{self.title}**")

        # Price and brand on same line
        price_line = f"💰 {self.price_bgn:.2f} лв ({self.price_eur:.2f} €)"
        if self.brand:
            price_line += f"  •  🏷️ {self.brand}"
        lines.append(price_line)

        # Description - clean formatting, smart truncation
        if self.description:
            desc = self.description[:300].strip()
            if len(self.description) > 300:
                # Cut at last complete sentence or word
                last_period = desc.rfind('.')
                if last_period > 200:
                    desc = desc[:last_period + 1]
                else:
                    desc = desc.rsplit(' ', 1)[0] + "..."
            lines.append(f"\n{desc}")

        # Add to cart link
        if self.product_url:
            lines.append(f"\n🛒 [Виж продукта / Купи]({self.product_url})")

        return "\n".join(lines)


@dataclass
class PipelineResult:
    """Result from the pipeline processing."""
    response: str
    is_medical: bool = True
    is_red_flag: bool = False
    original_text: str = ""
    translated_text: str = ""
    medical_reasoning: Optional[MedicalReasoning] = None
    candidate_products: list = field(default_factory=list)  # Stage 1: top-K from vector DB
    selected_products: list = field(default_factory=list)   # Stage 2: LLM-refined selection
    # Contraindication filtering results
    user_conditions: list = field(default_factory=list)  # Detected user conditions (pregnancy, diabetes, etc.)
    contraindicated_products: list = field(default_factory=list)  # Products filtered due to contraindications


class Pipeline:
    """
    Main pipeline that orchestrates all processing steps.

    Uses Perplexity-style two-stage retrieval:
    - Stage 1: Fast vector search for candidates
    - Stage 2: LLM refinement for best matches
    """

    # =========================================================================
    # Catalog Query Detection - Skip medical reasoning for product-only queries
    # =========================================================================
    _CATALOG_PATTERNS_BG = [
        # "What brands of X do you have/offer?"
        re.compile(r'какви\s+марки?\s+.+\s+(имате|предлагате|продавате)', re.IGNORECASE),
        re.compile(r'какви\s+.+\s+марки?\s+(имате|предлагате|продавате)', re.IGNORECASE),
        # "Show me X" / "I'm looking for X"
        re.compile(r'^покажи\s+(ми\s+)?', re.IGNORECASE),
        re.compile(r'^търся\s+', re.IGNORECASE),
        # "Do you have X?"
        re.compile(r'^имате\s+ли\s+', re.IGNORECASE),
        re.compile(r'^предлагате\s+ли\s+', re.IGNORECASE),
        re.compile(r'^продавате\s+ли\s+', re.IGNORECASE),
        # "What X do you have?"
        re.compile(r'^какви?\s+.+\s+(имате|предлагате)\s*\??$', re.IGNORECASE),
        # "List of X" / "All X"
        re.compile(r'^списък\s+(с|на)\s+', re.IGNORECASE),
        re.compile(r'^всички\s+', re.IGNORECASE),
        # Brand-specific queries
        re.compile(r'^продукти\s+(на|от)\s+', re.IGNORECASE),
    ]

    _CATALOG_PATTERNS_EN = [
        re.compile(r'what\s+brands?\s+of\s+.+\s+(do you have|do you offer|are available)', re.IGNORECASE),
        re.compile(r'^show\s+me\s+', re.IGNORECASE),
        re.compile(r'^looking\s+for\s+', re.IGNORECASE),
        re.compile(r'^do\s+you\s+(have|sell|offer)\s+', re.IGNORECASE),
        re.compile(r'^list\s+(of\s+)?', re.IGNORECASE),
        re.compile(r'^all\s+.+\s+products', re.IGNORECASE),
    ]

    # Product categories that indicate catalog queries (no symptoms)
    _CATALOG_CATEGORIES = {
        # Bulgarian - cosmetics/skincare
        'слънцезащитн', 'крем', 'кремове', 'лосион', 'шампоан', 'паста за зъби',
        'дезодорант', 'парфюм', 'козметика', 'грижа за кожа', 'грижа за коса',
        'серум', 'маска за лице', 'балсам', 'гел за душ', 'сапун',
        # Bulgarian - baby/hygiene
        'бебешки продукти', 'памперси', 'мокри кърпички', 'превръзки',
        # Bulgarian - supplements (non-symptom queries)
        'витамини', 'хранителни добавки', 'протеин', 'колаген', 'омега',
        # Bulgarian - medical devices
        'термометър', 'тонометър', 'глюкомер', 'инхалатор',
        # English equivalents
        'sunscreen', 'cream', 'lotion', 'shampoo', 'toothpaste',
        'deodorant', 'perfume', 'cosmetics', 'skincare', 'haircare',
        'diapers', 'wipes', 'bandages', 'vitamins', 'supplements',
    }

    def __init__(self, lazy_load: bool = True):
        """
        Initialize the pipeline.

        Args:
            lazy_load: If True, models are loaded on first use. If False, load immediately.
        """
        # Initialize intent classifier and safety layer
        self.intent_classifier = get_intent_classifier()
        self.safety_layer = get_safety_layer()

        # Product store (ChromaDB)
        self._product_store = None

        # Models (lazy loaded by default for faster startup)
        self._medical_model = None
        self._translator = None
        self._lazy_load = lazy_load

        if not lazy_load:
            self._load_medical_model()
            self._load_translator()
            self._load_product_store()

    @property
    def product_store(self):
        """Get the product store, loading lazily if necessary."""
        if self._product_store is None:
            self._product_store = get_product_store()
        return self._product_store

    @property
    def translator(self):
        """Get the translator, loading lazily if necessary."""
        if self._translator is None:
            self._translator = get_translator()
        return self._translator

    @property
    def medical_model(self):
        """Get the medical model, loading lazily if necessary."""
        if self._medical_model is None:
            self._medical_model = get_medical_model()
            self._medical_model.load()
        return self._medical_model

    def _load_product_store(self):
        """Load the product store."""
        if self._product_store is None:
            self._product_store = get_product_store()

    def _load_translator(self):
        """Load the translator models."""
        if self._translator is None:
            self._translator = get_translator()
            self._translator.load_all()

    def _load_medical_model(self):
        """Load the MedGemma model."""
        if self._medical_model is None:
            self._medical_model = get_medical_model()
            self._medical_model.load()

    # =========================================================================
    # Catalog Query Detection & Processing
    # =========================================================================
    def _is_catalog_query(self, text: str) -> tuple[bool, str]:
        """
        Detect if query is a product catalog inquiry (not a medical symptom query).

        Returns:
            Tuple of (is_catalog, search_term)
            - is_catalog: True if this is a catalog/product listing query
            - search_term: Extracted product category for search
        """
        text_lower = text.lower().strip()

        # Check Bulgarian patterns
        for pattern in self._CATALOG_PATTERNS_BG:
            if pattern.search(text_lower):
                # Extract the product category from the query
                search_term = self._extract_catalog_search_term(text)
                if search_term:
                    logger.debug(f"Catalog query detected (BG pattern)", extra={"search_term": search_term})
                    return True, search_term

        # Check English patterns
        for pattern in self._CATALOG_PATTERNS_EN:
            if pattern.search(text_lower):
                search_term = self._extract_catalog_search_term(text)
                if search_term:
                    logger.debug(f"Catalog query detected (EN pattern)", extra={"search_term": search_term})
                    return True, search_term

        # Check if query contains catalog category keywords without symptom words
        has_category = any(cat in text_lower for cat in self._CATALOG_CATEGORIES)
        has_symptom = self._has_symptom_words(text_lower)

        if has_category and not has_symptom:
            search_term = self._extract_catalog_search_term(text)
            if search_term:
                logger.debug(f"Catalog query detected (category keyword)", extra={"search_term": search_term})
                return True, search_term

        return False, ""

    def _extract_catalog_search_term(self, text: str) -> str:
        """Extract the product category/search term from a catalog query."""
        text_lower = text.lower()

        # Remove common question words to get the product term
        remove_patterns = [
            r'какви\s+марки?\s+(на\s+)?',
            r'какви\s+',
            r'имате\s+ли\s+',
            r'предлагате\s+ли\s+',
            r'продавате\s+ли\s+',
            r'покажи\s+(ми\s+)?',
            r'търся\s+',
            r'списък\s+(с|на)\s+',
            r'всички\s+',
            r'продукти\s+(на|от)\s+',
            r'\s+(имате|предлагате|продавате)\s*\??$',
            r'^what\s+brands?\s+of\s+',
            r'^show\s+me\s+',
            r'^looking\s+for\s+',
            r'^do\s+you\s+(have|sell|offer)\s+',
            r'^list\s+(of\s+)?',
            r'\s+(do you have|do you offer|are available)\s*\??$',
        ]

        result = text_lower
        for pattern in remove_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # Clean up
        result = result.strip(' ?.,!').strip()
        return result if len(result) > 2 else ""

    _SYMPTOM_WORDS = {
        'болка', 'боли', 'болки', 'температура', 'треска', 'кашлица',
        'хрема', 'гадене', 'повръщане', 'диария', 'запек', 'сърбеж',
        'обрив', 'подуване', 'възпаление', 'инфекция', 'алергия',
        'pain', 'ache', 'fever', 'cough', 'nausea', 'rash', 'swelling',
    }

    def _has_symptom_words(self, text: str) -> bool:
        """Check if text contains symptom-related words."""
        return any(symptom in text for symptom in self._SYMPTOM_WORDS)

    def _process_catalog_query(self, user_input: str, search_term: str) -> PipelineResult:
        """
        Process a catalog query without medical reasoning.

        This is the fast path for "What brands of X do you have?" type queries.
        Now uses hybrid search for better brand/product name matching.
        """
        start_time = time.perf_counter()
        logger.info(f"Processing catalog query", extra={"search_term": search_term})

        # Direct product search - no medical reasoning needed
        if self.product_store.collection.count() == 0:
            logger.warning("Product store is empty")
            return PipelineResult(
                response="Съжалявам, каталогът с продукти не е зареден.",
                is_medical=True,
                original_text=user_input
            )

        # Use hybrid search for better brand/product name matching
        results = self.product_store.hybrid_search(search_term, n_results=6)
        products = self._convert_to_products(results)

        # Filter OTC only
        products = self.safety_layer.filter_otc_only(products)

        # Format catalog response (simpler than medical response)
        response = self._format_catalog_response(search_term, products)

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Catalog query completed", extra={
            "duration_ms": round(duration_ms, 2),
            "products_found": len(products)
        })

        return PipelineResult(
            response=response,
            is_medical=True,  # Still pharmacy-related
            is_red_flag=False,
            original_text=user_input,
            candidate_products=products,
            selected_products=products[:3]
        )

    def _format_catalog_response(self, search_term: str, products: list) -> str:
        """Format a simple catalog response without medical analysis."""
        parts = []

        # Header
        parts.append(f"## 🛒 Продукти: {search_term.title()}\n")

        if products:
            # Group by brand if multiple products
            brands = set()
            for product in products:
                if isinstance(product, Product) and product.brand:
                    brands.add(product.brand)

            if brands:
                parts.append(f"**Налични марки:** {', '.join(sorted(brands))}\n")

            parts.append("### Продукти в наличност:\n")

            for i, product in enumerate(products[:5], 1):
                if isinstance(product, Product):
                    parts.append(f"**{i}. {product.to_display_string()}**\n")
                else:
                    parts.append(f"**{i}.** {product}\n")

            # Prompt for more specific needs
            parts.append("\n---")
            parts.append("*Имате ли специфични изисквания (SPF фактор, тип кожа, за деца)?*")
            parts.append("*Опишете ги и ще ви препоръчам най-подходящия продукт.*")
        else:
            parts.append(f'*Съжалявам, не намерих продукти за "{search_term}" в каталога.*')
            parts.append("\n*Опитайте с друга ключова дума или опишете за какво ви е нужен продуктът.*")

        return "\n".join(parts)

    def process(self, user_input: str) -> PipelineResult:
        """
        Process user input through the full pipeline.

        Steps:
        1. Intent Classification - is this a medical query?
        2. Translate BG → EN
        3. Medical Reasoning (MedGemma) - understand symptoms
        4. Safety Check (red flags, OTC only)
        5a. Product Retrieval (Vector DB) - get top-K candidates [FAST]
        5b. Product Refinement (LLM) - pick best matches [ACCURATE]
        6. Translate EN → BG
        7. Format Response
        """
        start_time = time.perf_counter()
        logger.info(f"Processing query", extra={
            "query_length": len(user_input),
            "query_preview": user_input[:50] + "..." if len(user_input) > 50 else user_input
        })

        # Step 0: Check for catalog queries (skip medical reasoning)
        is_catalog, search_term = self._is_catalog_query(user_input)
        if is_catalog:
            return self._process_catalog_query(user_input, search_term)

        # Step 1: Intent Classification
        is_medical, confidence, reason = self.intent_classifier.is_medical_query(user_input)
        logger.debug(f"Intent classification", extra={
            "is_medical": is_medical,
            "confidence": confidence,
            "reason": reason
        })
        if not is_medical:
            return PipelineResult(
                response=self.intent_classifier.get_rejection_message("bg", reason),
                is_medical=False,
                original_text=user_input
            )

        # Step 2: Translate BG → EN
        translated = self._translate_to_english(user_input)

        # Step 3: Medical Reasoning - understand symptoms and suggest treatment types
        medical_reasoning = self._get_medical_reasoning(translated)

        # Step 3b: Extract user conditions from both BG and EN text
        conditions_bg = extract_user_conditions(user_input)
        conditions_en = extract_user_conditions(translated)
        all_conditions = list(set(conditions_bg + conditions_en))
        if all_conditions:
            medical_reasoning.user_conditions = all_conditions
            logger.info(f"User conditions detected: {all_conditions}")

        # Check if MedGemma refused to help (non-medical query slipped through)
        if self._is_refusal_response(medical_reasoning):
            return PipelineResult(
                response=self.intent_classifier.get_rejection_message("bg"),
                is_medical=False,
                original_text=user_input,
                translated_text=translated,
                medical_reasoning=medical_reasoning
            )

        # Step 4: Safety Check (check BOTH original Bulgarian and translated English)
        is_red_flag, safety_message = self._check_safety(user_input, translated, medical_reasoning)
        logger.debug(f"Safety check", extra={"is_red_flag": is_red_flag})
        if is_red_flag:
            logger.warning(f"Red flag detected, referring to doctor")
            # Safety messages are already in Bulgarian, no translation needed
            return PipelineResult(
                response=safety_message,
                is_medical=True,
                is_red_flag=True,
                original_text=user_input,
                translated_text=translated,
                medical_reasoning=medical_reasoning
            )

        # Step 5a: Product Retrieval - Vector DB returns top-K candidates (FAST)
        candidate_products = self._retrieve_product_candidates(medical_reasoning)
        logger.debug(f"Vector search returned {len(candidate_products)} candidates")

        # Filter to OTC-only products
        candidate_products = self.safety_layer.filter_otc_only(candidate_products)

        # Step 5a2: Filter by contraindications based on user conditions
        contraindicated_products = []
        if medical_reasoning.user_conditions:
            candidate_products, contraindicated_products = filter_by_contraindications(
                products=candidate_products,
                user_conditions=medical_reasoning.user_conditions,
                strict=True  # Completely exclude contraindicated products
            )
            logger.info(
                f"Contraindication filter: {len(candidate_products)} safe, "
                f"{len(contraindicated_products)} removed"
            )

        # Step 5b: Product Refinement - LLM picks best matches (ACCURATE)
        selected_products = self._refine_product_selection(
            user_query=translated,
            medical_reasoning=medical_reasoning,
            candidates=candidate_products
        )

        # Check for warning-level symptoms (not blocking, but add message)
        warning_result = self.safety_layer.check_safety(user_input)

        # Step 6 & 7: Translate back and format response
        final_response = self._format_response(
            medical_reasoning=medical_reasoning,
            products=selected_products
        )

        # Add warning message if applicable
        final_response = self.safety_layer.add_safety_disclaimer(final_response, warning_result)

        # Add child-specific disclaimer if query is about children/babies
        if self._is_child_related_query(user_input):
            final_response = self._add_child_disclaimer(final_response)

        # Add safety information disclaimer for medication safety questions
        if self._is_safety_information_query(user_input):
            final_response = self._add_safety_info_disclaimer(final_response)

        # Add prescription warning for chronic disease queries
        if self._is_chronic_disease_query(user_input):
            final_response = self._add_chronic_disease_disclaimer(final_response)

        # Add contraindication warning if products were filtered
        if contraindicated_products:
            final_response = self._add_contraindication_warning(
                final_response,
                contraindicated_products,
                all_conditions
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"Pipeline completed", extra={
            "duration_ms": round(duration_ms, 2),
            "candidates": len(candidate_products),
            "selected": len(selected_products),
            "contraindicated": len(contraindicated_products),
            "user_conditions": all_conditions,
            "is_red_flag": False
        })

        return PipelineResult(
            response=final_response,
            is_medical=True,
            is_red_flag=False,
            original_text=user_input,
            translated_text=translated,
            medical_reasoning=medical_reasoning,
            candidate_products=candidate_products,
            selected_products=selected_products,
            user_conditions=all_conditions,
            contraindicated_products=contraindicated_products
        )

    # Phrases indicating the model refused to help (English and Bulgarian)
    _REFUSAL_PHRASES = {
        # English
        "i cannot", "i can't", "i'm not able to", "i am not able to",
        "i will not", "i won't", "cannot fulfill", "can't fulfill",
        "cannot help with", "can't help with", "not appropriate",
        "inappropriate request", "decline to", "refuse to",
        "against my guidelines", "violates my guidelines",
        "not a medical", "isn't a medical", "is not a medical",
        # Bulgarian
        "не мога", "не съм в състояние", "не е възможно",
        "не е подходящо", "неподходящ", "отказвам",
        "не е медицински", "това не е",
    }

    def _is_refusal_response(self, reasoning: MedicalReasoning) -> bool:
        """
        Check if MedGemma's response indicates it cannot or will not help.

        This catches cases where inappropriate queries slip through the intent
        classifier but MedGemma refuses to respond.
        """
        if not reasoning or not reasoning.likely_cause:
            return False

        response_lower = reasoning.likely_cause.lower()
        return any(phrase in response_lower for phrase in self._REFUSAL_PHRASES)

    def _translate_to_english(self, text: str) -> str:
        """Translate Bulgarian to English."""
        return self.translator.translate_to_english(text)

    def _translate_to_bulgarian(self, text: str) -> str:
        """Translate English to Bulgarian."""
        return self.translator.translate_to_bulgarian(text)

    def _get_medical_reasoning(self, text: str) -> MedicalReasoning:
        """
        Use MedGemma to understand symptoms and suggest treatment categories.

        Includes fallback strategy for graceful degradation if model fails.
        """
        try:
            return self.medical_model.get_medical_reasoning(text)
        except Exception as e:
            logger.error(f"MedGemma inference failed: {e}", exc_info=True)
            return self._create_fallback_reasoning(text)

    def _create_fallback_reasoning(self, text: str) -> MedicalReasoning:
        """
        Create a safe fallback MedicalReasoning when MedGemma fails.

        Returns a conservative response that recommends consulting a pharmacist.
        """
        logger.warning("Using fallback medical reasoning due to model failure")

        # Extract basic symptoms from text using simple keyword detection
        symptom_keywords = {
            "headache": ["главоболие", "headache", "болка в главата"],
            "fever": ["температура", "fever", "треска"],
            "cough": ["кашлица", "cough"],
            "pain": ["болка", "pain", "боли"],
            "cold": ["настинка", "cold", "простуда"],
            "stomach": ["стомах", "stomach", "корем"],
            "throat": ["гърло", "throat"],
        }

        detected_symptoms = []
        text_lower = text.lower()
        for symptom, keywords in symptom_keywords.items():
            if any(kw in text_lower for kw in keywords):
                detected_symptoms.append(symptom)

        return MedicalReasoning(
            symptoms=detected_symptoms if detected_symptoms else ["described symptoms"],
            likely_cause="Unable to perform detailed analysis",
            treatment_type="general wellness products",
            warnings=[
                "Automated analysis unavailable - please consult a pharmacist",
                "If symptoms persist or worsen, see a doctor"
            ],
            see_doctor=False,
            explanation="Our medical analysis system is temporarily limited. "
                       "We can show you general wellness products that may help.",
            how_treatment_helps="",
            self_care_tips=["Rest and stay hydrated", "Monitor your symptoms"],
            duration_guidance="Consult a pharmacist for personalized advice",
            user_conditions=[]
        )

    def _check_safety(self, original_query: str, translated_query: str, medical_reasoning: MedicalReasoning) -> tuple[bool, str]:
        """
        Check for red-flag symptoms requiring professional medical attention.

        Checks both original Bulgarian and translated English text for safety patterns,
        plus MedGemma's see_doctor recommendation.

        Returns (is_red_flag, message):
        - True means STOP and return safety message (no products)
        - False means CONTINUE with product search (may still add warnings later)
        """
        # Check original Bulgarian text for actual emergencies
        result = self.safety_layer.check_safety(original_query)
        if result.is_red_flag:
            return True, result.message

        # Check translated English text for actual emergencies
        result_en = self.safety_layer.check_safety(translated_query)
        if result_en.is_red_flag:
            return True, result_en.message

        # For MedGemma's see_doctor recommendation, handle differently based on query type
        if medical_reasoning.see_doctor:
            # For child-related queries, DON'T block - continue to find products
            # but add pediatric warnings (handled by _add_child_disclaimer later)
            if self._is_child_related_query(original_query):
                logger.info("Child query with see_doctor=True - proceeding with pediatric warnings")
                return False, ""  # Continue to product search

            # For pregnancy-related queries, DON'T block - continue with warnings
            if self._is_pregnancy_related_query(original_query):
                logger.info("Pregnancy query with see_doctor=True - proceeding with warnings")
                return False, ""  # Continue to product search

            # For drug combination/interaction queries, DON'T block - these are valid OTC questions
            # (e.g., "Can I take ibuprofen with paracetamol?")
            if self._is_drug_combination_query(original_query):
                logger.info("Drug combination query with see_doctor=True - proceeding with info")
                return False, ""  # Continue to provide helpful information

            # For other queries, use the generic doctor recommendation
            return True, (
                "⚠️ **Препоръчваме консултация с лекар.**\n\n"
                "Базирано на вашите симптоми, препоръчваме да се консултирате "
                "с медицински специалист за правилна диагноза и лечение."
            )

        return False, ""

    def _is_pregnancy_related_query(self, text: str) -> bool:
        """Check if query mentions pregnancy or breastfeeding."""
        text_lower = text.lower()
        pregnancy_keywords = {
            'бременна', 'бременност', 'бременни', 'бременността',
            'кърмя', 'кърмене', 'кърмачка', 'кърмещи',
            'pregnant', 'pregnancy', 'breastfeeding', 'nursing', 'lactating',
        }
        return any(kw in text_lower for kw in pregnancy_keywords)

    def _is_drug_combination_query(self, text: str) -> bool:
        """Check if query is about combining/taking multiple medications together.

        These are valid OTC questions like "Can I take ibuprofen with paracetamol?"
        """
        text_lower = text.lower()

        # Keywords indicating drug combination questions
        combination_keywords = {
            # Bulgarian
            'заедно с', 'едновременно', 'комбинирам', 'комбиниране',
            'смесвам', 'да взема с', 'взема с', 'приемам с',
            'може ли да взема', 'мога ли да взема',
            'може ли да приема', 'мога ли да приема',
            'да пия с', 'пия с', 'съчетавам', 'съчетание',
            # English
            'together with', 'at the same time', 'combine', 'combining',
            'mix', 'take with', 'can i take', 'can i use',
            'along with', 'in combination',
        }

        # Check for combination keywords
        has_combination_keyword = any(kw in text_lower for kw in combination_keywords)

        # Also check for pattern: two drug names mentioned
        common_otc_drugs = {
            'ибупрофен', 'ibuprofen', 'парацетамол', 'paracetamol', 'acetaminophen',
            'аспирин', 'aspirin', 'нурофен', 'nurofen', 'панадол', 'panadol',
            'адвил', 'advil', 'тайленол', 'tylenol', 'аналгин', 'analgin',
            'темпалгин', 'темпра', 'ефералган', 'efferalgan',
        }
        drugs_mentioned = sum(1 for drug in common_otc_drugs if drug in text_lower)

        return has_combination_keyword or drugs_mentioned >= 2

    def _retrieve_product_candidates(self, medical_reasoning: MedicalReasoning, top_k: int = 10) -> list:
        """
        Stage 1: Fast vector similarity search to get top-K product candidates.

        Uses ChromaDB with multilingual embeddings based on MedGemma's analysis.
        Now uses hybrid search (semantic + keyword) with category awareness.
        """
        if self.product_store.collection.count() == 0:
            logger.warning("Product store is empty. Run product_store.py --reload to load products.")
            return []

        search_query = self._build_search_query(medical_reasoning)

        # Use category-aware hybrid search for better results
        if medical_reasoning.treatment_type:
            results = self.product_store.search_by_category(
                query=search_query,
                treatment_type=medical_reasoning.treatment_type,
                n_results=top_k,
            )
        else:
            # Fallback to hybrid search without category
            results = self.product_store.hybrid_search(search_query, n_results=top_k)

        return self._convert_to_products(results)

    def _build_search_query(self, medical_reasoning: MedicalReasoning) -> str:
        """Build search query from medical reasoning components."""
        parts = []
        if medical_reasoning.treatment_type:
            parts.append(medical_reasoning.treatment_type)
        if medical_reasoning.symptoms:
            parts.extend(medical_reasoning.symptoms)
        if medical_reasoning.likely_cause:
            parts.append(medical_reasoning.likely_cause)
        return " ".join(parts) if parts else "medicine"

    def _convert_to_products(self, results: list) -> list:
        """Convert ChromaDB results to Product objects."""
        products = []
        for result in results:
            try:
                products.append(Product.from_chromadb(result))
            except Exception as e:
                logger.warning(f"Failed to parse product", extra={"error": str(e)})
        return products

    def _refine_product_selection(
        self,
        user_query: str,
        medical_reasoning: MedicalReasoning,
        candidates: list,
        max_products: int = 3
    ) -> list:
        """Stage 2: Use LLM to pick the best products from candidates."""
        if not candidates:
            return []

        # Build comprehensive reasoning string with user conditions
        reasoning_parts = [
            f"Symptoms: {', '.join(medical_reasoning.symptoms)}",
            f"Likely cause: {medical_reasoning.likely_cause}",
            f"Treatment type: {medical_reasoning.treatment_type}",
        ]

        # Add user conditions if present
        if medical_reasoning.user_conditions:
            conditions_str = ", ".join(medical_reasoning.user_conditions)
            reasoning_parts.append(f"User conditions: {conditions_str}")
            reasoning_parts.append(
                "IMPORTANT: Products must be safe for the user's conditions. "
                "Avoid recommending anything that could be contraindicated."
            )

        reasoning_str = ". ".join(reasoning_parts) + "."

        selected = self.medical_model.refine_product_selection(
            user_query=user_query,
            medical_reasoning=reasoning_str,
            candidate_products=candidates,
            max_products=max_products + 2,  # Get extra for deduplication
        )

        # Deduplicate by active ingredient to ensure variety
        deduplicated = self._deduplicate_by_ingredient(selected, max_products)

        return deduplicated

    def _deduplicate_by_ingredient(
        self,
        products: list,
        max_products: int,
        max_per_ingredient: int = 1
    ) -> list:
        """
        Deduplicate products by active ingredient to ensure recommendation variety.

        Prevents recommending 3 versions of the same drug (e.g., 3 ibuprofen brands).

        Args:
            products: List of Product objects
            max_products: Maximum products to return
            max_per_ingredient: Maximum products per active ingredient

        Returns:
            Deduplicated list of products
        """
        if not products:
            return []

        # Common active ingredients to detect (Bulgarian + English)
        INGREDIENT_PATTERNS = {
            "ibuprofen": ["ибупрофен", "ibuprofen", "нурофен", "бруфен"],
            "paracetamol": ["парацетамол", "paracetamol", "acetaminophen", "панадол", "ефералган"],
            "aspirin": ["аспирин", "aspirin", "ацетилсалицилова"],
            "diclofenac": ["диклофенак", "diclofenac", "волтарен"],
            "naproxen": ["напроксен", "naproxen", "налгезин"],
            "loratadine": ["лоратадин", "loratadine", "кларитин"],
            "cetirizine": ["цетиризин", "cetirizine", "зиртек"],
            "omeprazole": ["омепразол", "omeprazole"],
            "dextromethorphan": ["декстрометорфан", "dextromethorphan"],
            "pseudoephedrine": ["псевдоефедрин", "pseudoephedrine"],
        }

        def extract_ingredient(product: Product) -> str:
            """Extract primary active ingredient from product."""
            composition = (product.composition or "").lower()
            title = (product.title or "").lower()
            combined = f"{composition} {title}"

            for ingredient, patterns in INGREDIENT_PATTERNS.items():
                if any(pattern in combined for pattern in patterns):
                    return ingredient

            # Fallback: use first word of title as pseudo-ingredient
            return title.split()[0] if title else "unknown"

        seen_ingredients: dict[str, int] = {}
        result = []

        for product in products:
            ingredient = extract_ingredient(product)
            count = seen_ingredients.get(ingredient, 0)

            if count < max_per_ingredient:
                result.append(product)
                seen_ingredients[ingredient] = count + 1
                logger.debug(f"Selected '{product.title}' (ingredient: {ingredient})")

                if len(result) >= max_products:
                    break
            else:
                logger.debug(f"Skipped '{product.title}' (duplicate ingredient: {ingredient})")

        return result

    # Child-related keywords for detection
    _CHILD_KEYWORDS = {
        'бебе', 'бебета', 'бебешки', 'бебешка', 'бебето',
        'дете', 'деца', 'детски', 'детска', 'детето',
        'новородено', 'кърмаче', 'малко дете',
        'месечно', 'годишно', 'месеца', 'години',
        'педиатър', 'педиатричен',
        'никнене на зъби', 'зъбки',
        'дозировка за дете', 'доза за дете',
        'за деца', 'за бебета',
        'baby', 'babies', 'infant', 'infants',
        'child', 'children', 'kid', 'kids',
        'toddler', 'newborn',
        'months old', 'years old',
        'pediatric', 'teething',
    }

    def _is_child_related_query(self, text: str) -> bool:
        """Check if query mentions children, babies, or age-related terms."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self._CHILD_KEYWORDS)

    # Safety information keywords
    _SAFETY_KEYWORDS = {
        'двойна доза', 'тройна доза', 'предозиране', 'предозирах',
        'максимална доза', 'максималната доза', 'колко мога да взема',
        'прекалено много', 'твърде много',
        'алкохол с', 'пия алкохол', 'комбинирам', 'смесвам',
        'взема заедно', 'едновременно',
        'безопасно ли е', 'опасно ли е', 'вредно ли е',
        'странични ефекти', 'странични действия', 'нежелани реакции',
        'противопоказания', 'да не взема',
        'по време на бременност', 'бременна', 'кърмене', 'кърмя',
        'double dose', 'overdose', 'maximum dose',
        'alcohol with', 'combine', 'mix medications',
        'safe to take', 'dangerous', 'harmful',
        'side effects', 'contraindications',
        'during pregnancy', 'pregnant', 'breastfeeding',
    }

    def _is_safety_information_query(self, text: str) -> bool:
        """Check if query asks about medication safety."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self._SAFETY_KEYWORDS)

    def _add_child_disclaimer(self, response: str) -> str:
        """Add child-specific safety disclaimer to response."""
        disclaimer = """
⚠️ **Важно за деца и бебета:**
- **Консултирайте се с педиатър** за правилната диагноза и лечение
- Винаги проверявайте възрастовите ограничения на опаковката
- Дозировката зависи от възрастта и теглото на детето
- За бебета под 6 месеца - винаги консултация с педиатър преди лекарства
- При съмнение, попитайте фармацевт за подходящата доза

🏠 **Общи съвети за грижа:**
- Следете температурата на детето редовно
- Осигурете достатъчно течности (вода, чай, бульон)
- Осигурете покой и почивка
- Наблюдавайте за влошаване на симптомите

🚨 **Потърсете незабавна помощ ако:**
- Температурата е над 39°C и не спада
- Детето отказва да пие течности
- Има затруднено дишане
- Появи се обрив или петна"""
        return response + "\n" + disclaimer

    def _add_safety_info_disclaimer(self, response: str) -> str:
        """Add medication safety disclaimer to response."""
        # Don't add if response already contains emergency message
        if "112" in response or "СПЕШНО" in response:
            return response

        disclaimer = """
💊 **Важна информация за безопасност:**
- Винаги спазвайте препоръчаната доза от листовката
- Не комбинирайте лекарства без консултация с фармацевт или лекар
- При съмнение за предозиране, обадете се на Токсикологичен център или 112
- Консултирайте се с лекар преди употреба при бременност или кърмене"""
        return response + "\n" + disclaimer

    # Chronic disease keywords
    _CHRONIC_KEYWORDS = {
        'диабет', 'диабетик', 'захарен диабет', 'инсулин',
        'кръвна захар', 'глюкоза',
        'щитовидна', 'щитовидната жлеза', 'тироксин',
        'хипотиреоидизъм', 'хипертиреоидизъм',
        'хипертония', 'високо кръвно', 'кръвно налягане',
        'сърдечна недостатъчност', 'аритмия',
        'холестерол', 'статини',
        'астма', 'бронхиална астма', 'хобб',
        'епилепсия', 'паркинсон', 'множествена склероза',
        'антидепресант', 'антипсихотик', 'шизофрения',
        'ревматоиден артрит', 'лупус', 'имуносупресор',
        'diabetes', 'insulin', 'blood sugar',
        'thyroid', 'hypothyroidism', 'hyperthyroidism',
        'hypertension', 'blood pressure',
        'asthma', 'copd',
        'epilepsy', 'parkinson',
        'antidepressant', 'antipsychotic',
    }

    def _is_chronic_disease_query(self, text: str) -> bool:
        """Check if query is about chronic disease medications."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self._CHRONIC_KEYWORDS)

    def _add_chronic_disease_disclaimer(self, response: str) -> str:
        """Add prescription warning for chronic disease queries."""
        # Don't add if response already refers to doctor
        if "консултация с лекар" in response.lower() or "112" in response:
            return response

        disclaimer = """
📋 **Важно за хронични заболявания:**
- Лекарствата за хронични заболявания обикновено се отпускат **по лекарска рецепта**
- Не променяйте дозировката без консултация с вашия лекар
- Мога да ви помогна с допълнителни продукти: тест ленти, глюкомери, хранителни добавки
- За предписани лекарства, моля консултирайте се с вашия лекар или фармацевт"""
        return response + "\n" + disclaimer

    # Condition name translations for user-friendly messages
    _CONDITION_NAMES_BG = {
        "pregnancy": "бременност",
        "breastfeeding": "кърмене",
        "child": "деца",
        "elderly": "възрастни хора",
        "diabetes": "диабет",
        "heart": "сърдечни заболявания",
        "kidney": "бъбречни проблеми",
        "liver": "чернодробни проблеми",
        "allergy": "алергии",
        "stomach": "стомашни проблеми",
        "asthma": "астма",
    }

    def _add_contraindication_warning(
        self,
        response: str,
        contraindicated_products: list[tuple],
        user_conditions: list[str]
    ) -> str:
        """
        Add warning about products filtered due to user's conditions.

        Args:
            response: Current response text
            contraindicated_products: List of (Product, matching_conditions) tuples
            user_conditions: List of detected user conditions

        Returns:
            Response with contraindication warning added
        """
        if not contraindicated_products or not user_conditions:
            return response

        # Translate conditions to Bulgarian
        conditions_bg = [
            self._CONDITION_NAMES_BG.get(c, c) for c in user_conditions
        ]
        conditions_str = ", ".join(conditions_bg)

        # Get product names that were filtered
        filtered_names = [p[0].title for p in contraindicated_products[:3]]
        if len(contraindicated_products) > 3:
            filtered_names.append(f"и още {len(contraindicated_products) - 3}")

        disclaimer = f"""
⚠️ **Внимание за вашето състояние ({conditions_str}):**
- Изключени са {len(contraindicated_products)} продукт(а) с противопоказания за вас
- Показваме само безопасни алтернативи
- Винаги консултирайте фармацевт преди употреба"""

        return response + "\n" + disclaimer

    # =========================================================================
    # GARBAGE PATTERNS - Filter low-quality text from responses
    # =========================================================================
    # These patterns detect text that shouldn't appear in user-facing responses:
    # - Drug leaflet boilerplate (side effects, contraindications)
    # - EU regulation fragments
    # - Translation artifacts and garbled text
    # - Medical jargon inappropriate for consumers
    # - Product catalog noise

    _GARBAGE_PATTERNS = {
        # -----------------------------------------------------------------
        # DRUG LEAFLET / PACKAGE INSERT TEXT
        # -----------------------------------------------------------------
        # Side effects sections
        "нежелани реакции", "странични ефекти", "неизвестна честота",
        "с неизвестна честота", "нежелана реакция", "възможни нежелани",
        "side effects", "unknown frequency", "adverse reactions",
        "много чести", "чести нежелани", "нечести нежелани", "редки нежелани",
        # Anatomical system categories
        "мускулно- скелетната", "съединителната тъкан",
        "нарушения на кожата", "подкожната тъкан",
        "инфекции и ефекти", "мястото на приложение",
        "стомашно-чревни нарушения", "чернодробни нарушения",
        "сърдечни нарушения", "дихателни нарушения",
        "нарушения на нервната", "психични нарушения",
        "репродуктивни нарушения", "ендокринни нарушения",
        # Contraindications boilerplate
        "свръхчувствителност към активното",
        "свръхчувствителност към някоя от помощните",
        "противопоказания: свръхчувствителност",
        "да не се прилага при пациенти с",
        # Dosage/storage instructions
        "препоръчителна доза е", "максимална дневна доза",
        "да се съхранява на място", "срок на годност",
        "след изтичане на срока", "да се пази от деца",
        # Pharmaceutical body parts (leaflet language)
        "семенна течност", "сперматогенеза", "ерекция",

        # -----------------------------------------------------------------
        # EU REGULATIONS / LEGAL TEXT
        # -----------------------------------------------------------------
        "емисиите на парникови", "парникови газове", "регламент",
        "европейския парламент", "европейски парламент", "съвета",
        "в съответствие с изискванията", "директива на ес",
        "в съответствие с регламент", "официален вестник",
        "европейска комисия", "държави членки",
        "специални условия на труд", "стоманодобивната промишленост",
        "техниките средства за подпомагане",

        # -----------------------------------------------------------------
        # REPEATED / INCOHERENT PHRASES
        # -----------------------------------------------------------------
        "болка в гърба, болка в гърба", "болка в корема, болка в корема",
        "главоболие, главоболие", "температура, температура",
        "не се препоръчва употребата", "да се каже, че",
        "консултирайте с вашия лекар или фармацевт",
        "този препарат", "лекарствен продукт",
        "човешки рекомбинантен човешки рекомбинантен",
        "рекомбинантен еритропоетин",
        "препоръчителни че",

        # -----------------------------------------------------------------
        # TRUNCATED / GARBLED TEXT
        # -----------------------------------------------------------------
        "(сърх)", "(Сърх)", "( сърх", "сърх)",
        "тол- сол", "сол- сол", "- сол-", "тол-сол",
        "( -", "- )", "( )", "(-)",
        "- -", "-- --", "---",
        "мои_____", "ст ст ст", "(д възможно най-",
        "таблетка на", "нетно вещество",
        "от с", "обучение",

        # -----------------------------------------------------------------
        # FRAGMENTS / NONSENSE / FILLER
        # -----------------------------------------------------------------
        "допринася за по-малко", "усили въздуха",
        "трябва да се вземат мерки",
        "както и да е, трябва", "както и да е",
        "в зависимост от състоянието",
        "да се избягва свързването",
        "по- малко от 6 месеца", "(по- малко от",
        "през последните три години", "cuts обикновено",

        # -----------------------------------------------------------------
        # IRRELEVANT CATEGORIES
        # -----------------------------------------------------------------
        "сметки и апарати", "зъбни протези", "трикотажни",
        "тарифен номер", "тарифна позиция",
        "митническа позиция", "стокова позиция",

        # -----------------------------------------------------------------
        # MEDICAL JARGON (too technical for consumers)
        # -----------------------------------------------------------------
        "забрана за употреба при пациенти",
        "лекувани с човешки",
        "клинични изпитвания", "рандомизирано проучване",
        "двойно-сляпо", "плацебо-контролирано",
        "фармакокинетика", "фармакодинамика",
        "бионаличност", "полуживот на елиминиране",
        "плазмена концентрация", "пиково ниво",
        "лекарствени взаимодействия с",
        "индуктор на cyp", "инхибитор на cyp",
        "p-гликопротеин",

        # -----------------------------------------------------------------
        # PHARMACEUTICAL CODES / TECHNICAL
        # -----------------------------------------------------------------
        "mg/ml", "мг/мл", "таблетки x",
        "atc код", "atc-код", "анатомо-терапевтична",
        "inn:", "международно непатентно",
        "партиден номер", "сериен номер",

        # -----------------------------------------------------------------
        # TRANSLATION ARTIFACTS
        # -----------------------------------------------------------------
        "в в ", "на на ", "за за ", "от от ", "с с ",  # Doubled prepositions
        "the the", "a a ", "an an ", "is is ",  # English doubles
        " ,", " .", " ;", " :",  # Space before punctuation

        # -----------------------------------------------------------------
        # PRODUCT CATALOG / E-COMMERCE NOISE
        # -----------------------------------------------------------------
        "добави в количка", "добави в любими",
        "виж повече", "виж всички", "покажи повече",
        "изчерпано количество", "очаквайте скоро",
        "безплатна доставка", "бърза доставка",
        "цена с ддс", "цена без ддс",
        "% отстъпка", "артикулен номер", "баркод:",

        # -----------------------------------------------------------------
        # INSURANCE / ADMINISTRATIVE (Bulgarian healthcare system)
        # -----------------------------------------------------------------
        "нзок", "здравна каса", "реимбурсиране",
        "протокол за лечение", "позитивен списък",

        # -----------------------------------------------------------------
        # TRANSLATION HALLUCINATIONS / WRONG CONTEXT
        # -----------------------------------------------------------------
        # Completely wrong medical terms for context
        "introna", "интрон", "интерферон",
        "хепатит", "hepatitis",  # Unless actually asking about hepatitis
        "отстраняване на газовете", "отстраняване на газове",
        "цацове и слитове", "слитове за маса",
        "най-често се налага лечение с",
        "с intron", "с интрон",
        # Industrial/technical garbage
        "индустриален", "промишлен",
        "производство на", "преработка на",
        # Nonsense phrases from bad translation
        "възможно най- малко време",
        "да се използва доза",
        "се прилага в рамките на 1 час",
        "терапията с вирусите",
        "майчино- съдово лечение",
        "химикали и подобни форми",
        "предразположени към",
        "спадове в температурата",
        "прави бебето удобно",
        "определената за тази цел възраст",
        "труд на човека",
        "условия на труд",
        "4. 7",  # EU regulation numbering
        "4.7 специални",
        # More truncated/garbled patterns
        "_____", "____", "___",
        " ст ", " ст,", ",ст,", "ст ст",
        "мои___", "мои____", "мои_____",
        # English fragments that shouldn't appear in BG output
        "keep baby", "offer fluids", "lightly dressed",
        "keep бебе", "keep дете",  # Mixed English/BG
        "immediate care if fever", "immediate care if",
        "if fever exceeds", "if temperature exceeds",
        " if ", " exceeds ",  # English conjunctions in BG text
        "lukewarm", "sponge bath",
        "seek medical", "medical attention",
        # Common English words that indicate bad translation
        "keep ", "should ", "usually ", "avoid ",
        "monitor ", "ensure ", "apply ",
        " and ", "worsen after", "symptoms worsen",
        "see doctor", "consult doctor",
        # Malformed text patterns
        "това е в.", "това е в,", "в. or", ", or ",
        "крайни нарушения", "нарушения на вкуса",
        "ставите инфекции", "инфекции, които",
        "\" вижте", "[\"", "\"]",
        # Numbers with spaces in wrong places
        "38 . 5", "38. 5",
    }

    def _format_response(
        self,
        medical_reasoning: MedicalReasoning,
        products: list,
        translate_reasoning: bool = True
    ) -> str:
        """Format the final response as a friendly pharmacy assistant.

        Uses batched translation for efficiency when translate_reasoning=True.
        """
        parts = ["## 🔍 Медицински анализ\n"]

        # Collect all texts to translate in one batch for efficiency
        if translate_reasoning:
            texts_to_translate = self._collect_texts_for_translation(medical_reasoning)
            translated_texts = self._batch_translate_texts(texts_to_translate)
        else:
            translated_texts = {}

        # Helper to get translated text - returns None if translation fails/garbage
        def get_translated(key: str, original: str, min_length: int = 3) -> str | None:
            if not original or len(original) <= min_length:
                return None
            if not translate_reasoning:
                return original
            translated = translated_texts.get(key, original)
            # If translation is garbage or still English, skip the field entirely
            if self._contains_garbage(translated):
                return None  # Don't return English original - skip the field
            return translated

        # Symptoms (translate using dedicated symptom translation)
        if medical_reasoning.symptoms:
            translated_symptoms = []
            for symptom in medical_reasoning.symptoms:
                if symptom and len(symptom) < 40:
                    # Use specialized symptom translation
                    translated = self.translator.translate_symptom(symptom)
                    if translated and not self._contains_garbage(translated):
                        translated_symptoms.append(translated)
            if translated_symptoms:
                parts.append(f"**🩺 Симптоми:** {', '.join(translated_symptoms)}\n")

        # Probable cause with explanation
        if cause := get_translated("likely_cause", medical_reasoning.likely_cause):
            parts.append(f"**🔬 Вероятна причина:** {cause}\n")

        if explanation := get_translated("explanation", medical_reasoning.explanation, min_length=10):
            parts.append(f"{explanation}\n")

        # Treatment recommendation
        if treatment := get_translated("treatment_type", medical_reasoning.treatment_type):
            parts.append(f"**💊 Препоръчано лечение:** {treatment}\n")

        if how_helps := get_translated("how_treatment_helps", medical_reasoning.how_treatment_helps, min_length=10):
            parts.append(f"*{how_helps}*\n")

        # Self-care tips (limit to 3 valid tips)
        if medical_reasoning.self_care_tips:
            valid_tips = []
            for i, tip in enumerate(medical_reasoning.self_care_tips):
                # Skip tips that are too short, too long, or contain garbage
                if not tip or len(tip) < 5 or len(tip) > 100:
                    continue
                translated_tip = get_translated(f"tip_{i}", tip, min_length=5)
                if translated_tip and len(translated_tip) < 100:
                    # Additional validation: must have some Bulgarian or be clearly useful
                    valid_tips.append(translated_tip)
                if len(valid_tips) >= 3:  # Limit to 3 tips
                    break
            if valid_tips:
                parts.append("**🏠 Домашни грижи:**")
                parts.extend(f"• {tip}" for tip in valid_tips)
                parts.append("")

        # Recovery timeline (skip if too long or contains jargon)
        if medical_reasoning.duration_guidance:
            duration = get_translated("duration_guidance", medical_reasoning.duration_guidance)
            # Skip if it looks like garbage (too long, contains drug names, etc.)
            if duration and len(duration) < 120 and not any(
                bad in duration.lower() for bad in ['intron', 'интрон', 'лечение с', 'терапия с']
            ):
                parts.append(f"**⏱️ Възстановяване:** {duration}\n")

        # Warnings
        if medical_reasoning.warnings:
            valid_warnings = []
            for i, warning in enumerate(medical_reasoning.warnings):
                translated_warning = get_translated(f"warning_{i}", warning, min_length=10)
                if translated_warning:
                    valid_warnings.append(translated_warning)
            if valid_warnings:
                parts.append("**⚠️ Кога да потърсите лекар:**")
                parts.extend(f"• {warning}" for warning in valid_warnings)
                parts.append("")

        # Product recommendations
        parts.append("\n## 💊 Препоръчани продукти\n")
        if products:
            for i, product in enumerate(products, 1):
                display = product.to_display_string() if isinstance(product, Product) else str(product)
                parts.append(f"### {i}. {display}\n")
        else:
            parts.append("*Съжалявам, не намерих подходящи продукти в каталога.*")

        if medical_reasoning.see_doctor:
            parts.append("\n🏥 **Важно:** Препоръчваме консултация с лекар за вашите симптоми.")

        parts.append("\n---")
        parts.append("*Това е информационна услуга, не медицински съвет. "
                    "Консултирайте се с фармацевт за повече информация.*")

        return "\n".join(parts)

    def _collect_texts_for_translation(self, medical_reasoning: MedicalReasoning) -> dict[str, str]:
        """Collect all texts from MedicalReasoning that need translation."""
        texts = {}

        # Symptoms
        if medical_reasoning.symptoms:
            for symptom in medical_reasoning.symptoms:
                if symptom and len(symptom) < 40:
                    texts[f"symptom_{symptom}"] = symptom

        if medical_reasoning.likely_cause:
            texts["likely_cause"] = medical_reasoning.likely_cause
        if medical_reasoning.explanation:
            texts["explanation"] = medical_reasoning.explanation
        if medical_reasoning.treatment_type:
            texts["treatment_type"] = medical_reasoning.treatment_type
        if medical_reasoning.how_treatment_helps:
            texts["how_treatment_helps"] = medical_reasoning.how_treatment_helps
        if medical_reasoning.duration_guidance:
            texts["duration_guidance"] = medical_reasoning.duration_guidance

        # Self-care tips
        if medical_reasoning.self_care_tips:
            for i, tip in enumerate(medical_reasoning.self_care_tips):
                if tip:
                    texts[f"tip_{i}"] = tip

        # Warnings
        if medical_reasoning.warnings:
            for i, warning in enumerate(medical_reasoning.warnings):
                if warning:
                    texts[f"warning_{i}"] = warning

        return texts

    def _batch_translate_texts(self, texts: dict[str, str]) -> dict[str, str]:
        """Batch translate all texts in one call for efficiency."""
        if not texts:
            return {}

        keys = list(texts.keys())
        values = list(texts.values())

        try:
            translated_values = self.translator.translate_batch_to_bulgarian(values)
            return dict(zip(keys, translated_values))
        except Exception as e:
            logger.warning(f"Batch translation failed, falling back to originals: {e}")
            return texts

    def _contains_garbage(self, text: str) -> bool:
        """Check if text contains garbage patterns, low Bulgarian content, or excessive repetition."""
        if not text or len(text.strip()) < 3:
            return True

        text_lower = text.lower()

        # Check for garbage patterns
        if any(pattern in text_lower for pattern in self._GARBAGE_PATTERNS):
            return True

        # Check Bulgarian content ratio (text should be mostly Bulgarian)
        bg_ratio = self._calculate_bulgarian_ratio(text)
        if bg_ratio < 0.3:  # Less than 30% Bulgarian = garbage for BG output
            return True

        # Check for excessive word repetition
        words = text_lower.split()
        if len(words) >= 5:
            from collections import Counter
            word_counts = Counter(words)
            # If any word appears more than 50% of the time, it's garbage
            max_count = max(word_counts.values())
            if max_count > len(words) * 0.5:
                return True

        # Check for 3-word phrase repetition
        if len(words) > 10:
            for i in range(len(words) - 5):
                phrase = " ".join(words[i:i+3])
                if text_lower.count(phrase) >= 3:
                    return True

        return False

    def _calculate_bulgarian_ratio(self, text: str) -> float:
        """Calculate the ratio of Bulgarian characters in text."""
        if not text:
            return 0.0
        bulgarian_chars = set("абвгдежзийклмнопрстуфхцчшщъьюя")
        text_lower = text.lower()
        bg_count = sum(1 for c in text_lower if c in bulgarian_chars)
        total_alpha = sum(1 for c in text_lower if c.isalpha())
        return bg_count / total_alpha if total_alpha > 0 else 0.0


# Global pipeline instance
_pipeline: Optional[Pipeline] = None


def get_pipeline() -> Pipeline:
    """Get or create the pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline
