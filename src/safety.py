"""
Safety Layer for detecting red-flag symptoms and enforcing OTC-only recommendations.

Uses a hybrid approach:
- Fast keyword matching for known dangerous phrases
- Semantic embedding matching for paraphrasing/typos/transliteration
- Unicode normalization to prevent bypass via lookalike characters
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from src.logging_config import get_logger
from src.safety_embeddings import get_embedding_safety_classifier

logger = get_logger("viapharma.safety")


# =============================================================================
# UNICODE NORMALIZATION
# =============================================================================

# Characters to remove (invisible/zero-width that could hide dangerous content)
INVISIBLE_CHARS = {
    '\u200b',  # Zero-width space
    '\u200c',  # Zero-width non-joiner
    '\u200d',  # Zero-width joiner
    '\ufeff',  # BOM / zero-width no-break space
    '\u00ad',  # Soft hyphen
    '\u2060',  # Word joiner
    '\u180e',  # Mongolian vowel separator
}


def normalize_text_for_safety(text: str) -> str:
    """
    Normalize text to prevent safety check bypass via unicode tricks.

    Handles:
    - Unicode normalization (NFKC form) - normalizes ligatures, fullwidth chars
    - Zero-width/invisible character removal
    - Excessive whitespace normalization

    Note: Does NOT convert Cyrillic to Latin - we support Bulgarian keywords.

    Args:
        text: Input text that may contain bypass attempts

    Returns:
        Normalized text safe for keyword matching
    """
    if not text:
        return ""

    # Step 1: Unicode normalization (NFKC - compatibility decomposition + canonical composition)
    # This normalizes things like ﬁ -> fi, ² -> 2, fullwidth -> ASCII, etc.
    # Importantly, it does NOT convert Cyrillic to Latin
    normalized = unicodedata.normalize('NFKC', text)

    # Step 2: Remove invisible/zero-width characters that could hide content
    normalized = ''.join(char for char in normalized if char not in INVISIBLE_CHARS)

    # Step 3: Remove remaining control characters (but keep newlines/tabs)
    normalized = ''.join(
        char for char in normalized
        if unicodedata.category(char) not in ('Cc', 'Cf') or char in '\n\t'
    )

    # Step 4: Normalize whitespace (but preserve newlines)
    normalized = re.sub(r'[^\S\n]+', ' ', normalized)
    normalized = re.sub(r'\n\s*\n', '\n\n', normalized)

    return normalized.strip()


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""
    is_red_flag: bool
    severity: str  # "none", "warning", "urgent", "emergency"
    matched_symptoms: list
    message: str
    should_refer_to_doctor: bool


class SafetyLayer:
    """
    Detects dangerous symptoms and ensures safe recommendations.

    Red-flag categories:
    - Emergency: Immediate medical attention needed
    - Urgent: Should see doctor soon
    - Warning: Monitor and seek help if worsens
    """

    def __init__(self):
        # Emergency symptoms - need immediate medical attention (call 112/911)
        self.emergency_symptoms = {
            # Bulgarian
            'не мога да дишам', 'задушавам се', 'затруднено дишане',
            'болка в гърдите', 'стягане в гърдите', 'натиск в гърдите',
            'силна болка в гърдите',
            'загуба на съзнание', 'припадък', 'припаднах',
            'не мога да говоря', 'невъзможност да говоря',
            'парализа', 'не мога да движа', 'изтръпване на лицето',
            'внезапно замъглено зрение', 'загуба на зрение',
            'силно кървене', 'не спира кръвта',
            'гърч', 'гърчове', 'епилептичен припадък',
            'анафилаксия', 'анафилактичен шок',
            'отравяне', 'отрових се', 'погълнах',
            'суицидни мисли', 'искам да се убия', 'самоубийство',

            # Bulgarian - poisoning/overdose (child-specific)
            'глътна хапче', 'глътнах хапче', 'изпих лекарство',
            'дете глътна', 'бебе глътна', 'детето ми глътна',
            'погълна батерия', 'изпи препарат', 'изпих препарат',
            'предозиране', 'предозирах', 'твърде много хапчета',

            # Bulgarian - mental health emergencies / self-harm
            'самонараня', 'самонараняване', 'да се нараня',
            'искам да умра', 'мисли за смърт', 'не искам да живея',
            'режа се', 'нараних се нарочно', 'искам да си навредя',

            # Bulgarian - severe allergic reactions
            'силна алергична реакция', 'тежка алергична реакция',
            'силна алергия', 'тежка алергия',
            'подуване на гърлото', 'оток на гърлото', 'подут език',
            'не мога да преглъщам', 'задушавам се от алергия',
            'обрив по цялото тяло', 'подуване на лицето',

            # Bulgarian transliteration (latinica)
            'ne moga da disham', 'zadushavam se', 'bolka v gardite',
            'iskam da se ubiya', 'iskam da umra', 'samonaranyavane',
            'deteto mi glatna', 'predozirah', 'otrovih se',

            # English
            "can't breathe", "cannot breathe", "difficulty breathing", "choking",
            "chest pain", "chest pressure", "chest tightness",
            "loss of consciousness", "fainted", "fainting",
            "can't speak", "cannot speak", "slurred speech",
            "paralysis", "can't move", "cannot move", "face drooping",
            "sudden vision loss", "sudden blindness",
            "severe bleeding", "won't stop bleeding",
            "seizure", "convulsion",
            "anaphylaxis", "anaphylactic shock",
            "poisoning", "overdose", "swallowed",
            "suicidal", "want to kill myself", "suicide",

            # English - severe allergic reactions
            "severe allergic reaction", "serious allergic reaction",
            "severe allergy", "throat swelling", "throat closing",
            "swollen tongue", "can't swallow", "whole body rash",
            "face swelling", "lips swelling",
        }

        # Urgent symptoms - should see doctor within 24-48 hours
        self.urgent_symptoms = {
            # Bulgarian
            'кръв в урината', 'кърваво уриниране',
            'кръв в изпражненията', 'черни изпражнения',
            'повръщане на кръв',
            'силна коремна болка', 'остра коремна болка',
            'висока температура над 39', 'температура 40',
            'температура повече от 3 дни', 'треска 3 дни',
            'силно главоболие', 'най-силното главоболие',
            'схванат врат', 'скован врат', 'не мога да наведа глава',
            'обрив с температура', 'петна по кожата с треска',
            'подуване на лицето', 'подут език', 'подути устни',
            'жълти очи', 'жълта кожа', 'жълтеница',
            'объркване', 'дезориентация', 'не разпознавам',
            'силна болка в гърба', 'болка в бъбреците',
            'болка при уриниране повече от 2 дни',
            'не съм уринирал', 'не мога да уринирам',

            # English
            'blood in urine', 'bloody urine',
            'blood in stool', 'black stool', 'bloody stool',
            'vomiting blood',
            'severe abdominal pain', 'acute stomach pain',
            'high fever over 39', 'fever 40', 'fever above 103',
            'fever for 3 days', 'fever lasting',
            'severe headache', 'worst headache ever', 'thunderclap headache',
            'stiff neck', 'neck stiffness', "can't bend neck",
            'rash with fever', 'spots with fever',
            'facial swelling', 'swollen tongue', 'swollen lips',
            'yellow eyes', 'yellow skin', 'jaundice',
            'confusion', 'disorientation', 'not recognizing',
            'severe back pain', 'kidney pain',
            'painful urination for days',
            "haven't urinated", "can't urinate", 'unable to urinate',
        }

        # Warning symptoms - monitor closely, see doctor if persists/worsens
        self.warning_symptoms = {
            # Bulgarian
            'кашлица повече от 2 седмици', 'продължителна кашлица',
            'загуба на тегло', 'отслабвам без причина',
            'нощно изпотяване', 'изпотявам се нощем',
            'умора повече от 2 седмици', 'постоянна умора',
            'бучка', 'възел', 'подутина',
            'промяна в бенка', 'бенка се промени',
            'рана която не зараства',
            'затруднено преглъщане', 'болка при преглъщане',
            'постоянна болка', 'болка която не минава',
            'повтарящо се кървене', 'кървене от носа често',
            'чести главоболия', 'главоболие всеки ден',
            'замъглено зрение', 'проблеми със зрението',
            'звънтене в ушите', 'загуба на слух',

            # English
            'cough for more than 2 weeks', 'persistent cough',
            'weight loss', 'losing weight without trying',
            'night sweats',
            'fatigue for weeks', 'constant fatigue',
            'lump', 'nodule', 'growth',
            'mole changed', 'changing mole',
            'wound not healing', 'sore not healing',
            'difficulty swallowing', 'painful swallowing',
            'persistent pain', 'pain that won\'t go away',
            'recurring bleeding', 'frequent nosebleeds',
            'frequent headaches', 'daily headaches',
            'blurred vision', 'vision problems',
            'ringing in ears', 'hearing loss',
        }

        # Compile patterns
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for symptom matching."""
        def make_pattern(keywords):
            escaped = [re.escape(kw) for kw in keywords]
            return re.compile('(' + '|'.join(escaped) + ')', re.IGNORECASE)

        self._emergency_pattern = make_pattern(self.emergency_symptoms)
        self._urgent_pattern = make_pattern(self.urgent_symptoms)
        self._warning_pattern = make_pattern(self.warning_symptoms)

    def check_safety(self, text: str, include_medical_reasoning: bool = True) -> SafetyCheckResult:
        """Check text for red-flag symptoms.

        Applies unicode normalization to prevent bypass via lookalike characters.
        """
        if not text:
            return self._safe_result()

        # Normalize text to prevent bypass via unicode tricks
        normalized_text = normalize_text_for_safety(text)
        text_lower = normalized_text.lower()

        # Check each severity level in order of priority
        for severity, pattern, is_red_flag in [
            ("emergency", self._emergency_pattern, True),
            ("urgent", self._urgent_pattern, True),
            ("warning", self._warning_pattern, False),
        ]:
            matches = pattern.findall(text_lower)
            if matches:
                unique_matches = list(set(matches))
                if is_red_flag:
                    logger.warning(f"{severity.upper()} symptoms detected", extra={
                        "severity": severity,
                        "matched": unique_matches
                    })
                return SafetyCheckResult(
                    is_red_flag=is_red_flag,
                    severity=severity,
                    matched_symptoms=unique_matches,
                    message=self._get_message_for_severity(severity),
                    should_refer_to_doctor=True
                )

        return self._safe_result()

    def _safe_result(self) -> SafetyCheckResult:
        """Return a safe (no issues) result."""
        return SafetyCheckResult(
            is_red_flag=False,
            severity="none",
            matched_symptoms=[],
            message="",
            should_refer_to_doctor=False
        )

    # Severity rankings for comparing results
    _SEVERITY_RANK = {"emergency": 4, "urgent": 3, "warning": 2, "none": 1, "safe": 1}

    def check_safety_hybrid(self, text: str) -> SafetyCheckResult:
        """
        Hybrid safety check: fast keywords + semantic embeddings.

        Applies unicode normalization and returns the most severe result from either method.
        """
        # Normalize before checking (check_safety also normalizes, but we need it for embedding too)
        normalized_text = normalize_text_for_safety(text)
        keyword_result = self.check_safety(normalized_text)

        # If keywords found emergency/urgent, return immediately
        if keyword_result.severity in ("emergency", "urgent"):
            return keyword_result

        # Run embedding check for semantic matching (use normalized text)
        try:
            embedding_classifier = get_embedding_safety_classifier()
            embedding_result = embedding_classifier.classify(normalized_text)
        except Exception as e:
            logger.error(f"Embedding classifier failed: {e}")
            return keyword_result

        # Compare severities, take the more severe
        keyword_rank = self._SEVERITY_RANK.get(keyword_result.severity, 0)
        embedding_rank = self._SEVERITY_RANK.get(embedding_result.severity, 0)

        if embedding_rank > keyword_rank:
            return SafetyCheckResult(
                is_red_flag=embedding_result.severity in ("emergency", "urgent"),
                severity=embedding_result.severity,
                matched_symptoms=[embedding_result.matched_phrase] if embedding_result.matched_phrase else [],
                message=self._get_message_for_severity(embedding_result.severity),
                should_refer_to_doctor=embedding_result.severity != "safe"
            )

        return keyword_result

    def check_safety_with_llm_result(
        self,
        text: str,
        llm_safety_level: str = "safe",
        llm_detected_flags: list = None,
    ) -> SafetyCheckResult:
        """
        Hybrid safety check: hard-coded fast-path + LLM augmentation.

        The hard-coded patterns ALWAYS run first (non-negotiable for safety).
        LLM results augment by catching paraphrases and semantic variations
        that keyword matching might miss.

        Args:
            text: User query text
            llm_safety_level: Safety level from unified LLM processor
                ("safe", "warning", "urgent", "emergency")
            llm_detected_flags: List of symptoms/flags detected by LLM

        Returns:
            SafetyCheckResult with the most severe finding from either source
        """
        if llm_detected_flags is None:
            llm_detected_flags = []

        # ALWAYS run hard-coded check first (non-negotiable)
        keyword_result = self.check_safety(text)

        # If hard-coded found emergency, return immediately
        if keyword_result.severity == "emergency":
            logger.info(
                "Hard-coded safety detected EMERGENCY",
                extra={"matched": keyword_result.matched_symptoms}
            )
            return keyword_result

        # If hard-coded found urgent, return immediately
        if keyword_result.severity == "urgent":
            logger.info(
                "Hard-coded safety detected URGENT",
                extra={"matched": keyword_result.matched_symptoms}
            )
            return keyword_result

        # Compare with LLM result - take the more severe
        llm_is_red_flag = llm_safety_level in ("emergency", "urgent")

        if llm_is_red_flag:
            # LLM detected something keywords missed (e.g., paraphrase)
            logger.info(
                "LLM safety augmentation detected red flag",
                extra={
                    "llm_level": llm_safety_level,
                    "llm_flags": llm_detected_flags,
                    "keyword_level": keyword_result.severity,
                }
            )
            return SafetyCheckResult(
                is_red_flag=True,
                severity=llm_safety_level,
                matched_symptoms=llm_detected_flags,
                message=self._get_message_for_severity(llm_safety_level),
                should_refer_to_doctor=True,
            )

        # LLM detected warning but keywords didn't
        if llm_safety_level == "warning" and keyword_result.severity == "none":
            return SafetyCheckResult(
                is_red_flag=False,
                severity="warning",
                matched_symptoms=llm_detected_flags,
                message=self._get_message_for_severity("warning"),
                should_refer_to_doctor=True,
            )

        # Return keyword result (could be warning or safe)
        return keyword_result

    # Pre-defined messages for each severity level
    _MESSAGES = {
        "emergency": """🚨 **СПЕШНО: Моля, потърсете незабавна медицинска помощ!**

Описаните симптоми изискват спешна медицинска намеса.

**Действия:**
- Обадете се на **112** (Спешна помощ)
- Отидете в най-близкото спешно отделение
- Не шофирайте сами, ако е възможно

⚠️ Този чатбот НЕ може да помогне при спешни медицински състояния.""",

        "urgent": """⚠️ **ВАЖНО: Препоръчваме консултация с лекар**

Описаните симптоми изискват медицински преглед в рамките на 24-48 часа.

**Препоръки:**
- Посетете личния си лекар възможно най-скоро
- Ако симптомите се влошат, потърсете спешна помощ
- Не отлагайте прегледа

ℹ️ Не препоръчваме самолечение при тези симптоми.""",

        "warning": """ℹ️ **Забележка:** Ако симптомите продължат повече от няколко дни или се влошат,
моля консултирайте се с лекар.""",
    }

    def _get_message_for_severity(self, severity: str) -> str:
        """Get appropriate message for a severity level."""
        return self._MESSAGES.get(severity, "")

    def filter_otc_only(self, products: list) -> list:
        """Filter products to only include OTC (over-the-counter) items."""
        return [p for p in products if getattr(p, 'is_otc', True)]

    def add_safety_disclaimer(self, response: str, safety_result: SafetyCheckResult) -> str:
        """Add appropriate safety disclaimer to response if needed."""
        if safety_result.severity == "warning" and safety_result.message:
            return f"{response}\n\n{safety_result.message}"
        return response


# Global instance
_safety_layer: Optional[SafetyLayer] = None


def get_safety_layer() -> SafetyLayer:
    """Get or create the global safety layer instance."""
    global _safety_layer
    if _safety_layer is None:
        _safety_layer = SafetyLayer()
    return _safety_layer
