"""
Safety Layer for detecting red-flag symptoms and enforcing OTC-only recommendations.

Ensures user safety by:
1. Detecting serious symptoms that require medical attention (keyword + semantic)
2. Filtering to only OTC (over-the-counter) products
3. Adding appropriate warnings and disclaimers

Uses a hybrid approach:
- Fast keyword matching for known dangerous phrases
- Semantic embedding matching for paraphrasing/typos/transliteration
"""

import re
from typing import Optional
from dataclasses import dataclass

from src.logging_config import get_logger
from src.safety_embeddings import get_embedding_safety_classifier, EmbeddingSafetyResult

logger = get_logger("viapharma.safety")


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
        """
        Check text for red-flag symptoms.

        Args:
            text: User query or medical reasoning to check
            include_medical_reasoning: Whether to also check medical reasoning

        Returns:
            SafetyCheckResult with severity and recommendations
        """
        if not text:
            return SafetyCheckResult(
                is_red_flag=False,
                severity="none",
                matched_symptoms=[],
                message="",
                should_refer_to_doctor=False
            )

        text_lower = text.lower()

        # Check for emergency symptoms
        emergency_matches = self._emergency_pattern.findall(text_lower)
        if emergency_matches:
            logger.warning(f"EMERGENCY symptoms detected", extra={
                "severity": "emergency",
                "matched": list(set(emergency_matches))
            })
            return SafetyCheckResult(
                is_red_flag=True,
                severity="emergency",
                matched_symptoms=list(set(emergency_matches)),
                message=self._get_emergency_message(),
                should_refer_to_doctor=True
            )

        # Check for urgent symptoms
        urgent_matches = self._urgent_pattern.findall(text_lower)
        if urgent_matches:
            logger.warning(f"URGENT symptoms detected", extra={
                "severity": "urgent",
                "matched": list(set(urgent_matches))
            })
            return SafetyCheckResult(
                is_red_flag=True,
                severity="urgent",
                matched_symptoms=list(set(urgent_matches)),
                message=self._get_urgent_message(),
                should_refer_to_doctor=True
            )

        # Check for warning symptoms
        warning_matches = self._warning_pattern.findall(text_lower)
        if warning_matches:
            return SafetyCheckResult(
                is_red_flag=False,  # Not a hard stop, but add warning
                severity="warning",
                matched_symptoms=list(set(warning_matches)),
                message=self._get_warning_message(),
                should_refer_to_doctor=True
            )

        return SafetyCheckResult(
            is_red_flag=False,
            severity="none",
            matched_symptoms=[],
            message="",
            should_refer_to_doctor=False
        )

    def check_safety_hybrid(self, text: str) -> SafetyCheckResult:
        """
        Hybrid safety check: fast keywords + semantic embeddings.

        Runs keyword check first (instant), then embedding check if needed.
        Returns the most severe result from either method.

        Args:
            text: User query to check

        Returns:
            SafetyCheckResult with the highest severity detected
        """
        # 1. Fast keyword check (existing)
        keyword_result = self.check_safety(text)

        # 2. If keywords found emergency/urgent, return immediately
        if keyword_result.severity in ("emergency", "urgent"):
            return keyword_result

        # 3. Run embedding check for semantic matching
        try:
            embedding_classifier = get_embedding_safety_classifier()
            embedding_result = embedding_classifier.classify(text)
        except Exception as e:
            logger.error(f"Embedding classifier failed: {e}")
            # Fall back to keyword result
            return keyword_result

        # 4. Compare severities, take the more severe
        severity_rank = {"emergency": 4, "urgent": 3, "warning": 2, "none": 1, "safe": 1}
        keyword_rank = severity_rank.get(keyword_result.severity, 0)
        embedding_rank = severity_rank.get(embedding_result.severity, 0)

        if embedding_rank > keyword_rank:
            # Embedding found something more severe
            return SafetyCheckResult(
                is_red_flag=embedding_result.severity in ("emergency", "urgent"),
                severity=embedding_result.severity,
                matched_symptoms=[embedding_result.matched_phrase] if embedding_result.matched_phrase else [],
                message=self._get_message_for_severity(embedding_result.severity),
                should_refer_to_doctor=embedding_result.severity != "safe"
            )

        return keyword_result

    def _get_message_for_severity(self, severity: str) -> str:
        """Get appropriate message for a severity level."""
        if severity == "emergency":
            return self._get_emergency_message()
        elif severity == "urgent":
            return self._get_urgent_message()
        elif severity == "warning":
            return self._get_warning_message()
        return ""

    def _get_emergency_message(self) -> str:
        """Get emergency response message in Bulgarian."""
        return """🚨 **СПЕШНО: Моля, потърсете незабавна медицинска помощ!**

Описаните симптоми изискват спешна медицинска намеса.

**Действия:**
- Обадете се на **112** (Спешна помощ)
- Отидете в най-близкото спешно отделение
- Не шофирайте сами, ако е възможно

⚠️ Този чатбот НЕ може да помогне при спешни медицински състояния."""

    def _get_urgent_message(self) -> str:
        """Get urgent response message in Bulgarian."""
        return """⚠️ **ВАЖНО: Препоръчваме консултация с лекар**

Описаните симптоми изискват медицински преглед в рамките на 24-48 часа.

**Препоръки:**
- Посетете личния си лекар възможно най-скоро
- Ако симптомите се влошат, потърсете спешна помощ
- Не отлагайте прегледа

ℹ️ Не препоръчваме самолечение при тези симптоми."""

    def _get_warning_message(self) -> str:
        """Get warning response message in Bulgarian."""
        return """ℹ️ **Забележка:** Ако симптомите продължат повече от няколко дни или се влошат,
моля консултирайте се с лекар."""

    def filter_otc_only(self, products: list) -> list:
        """
        Filter products to only include OTC (over-the-counter) items.

        Args:
            products: List of Product objects

        Returns:
            List of only OTC products
        """
        return [p for p in products if getattr(p, 'is_otc', True)]

    def add_safety_disclaimer(self, response: str, safety_result: SafetyCheckResult) -> str:
        """
        Add appropriate safety disclaimer to response.

        Args:
            response: The chatbot response
            safety_result: Result from safety check

        Returns:
            Response with safety disclaimer added
        """
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
