"""
Response validation and text quality checking for the ViaPharma pipeline.

Handles:
- Garbage text detection (LLM hallucinations, translation artifacts)
- Bulgarian language ratio validation
- English leak detection and cleaning
- Self-care tip validation
- Sentence-level filtering

Extracted from orchestrator.py as part of Issue #2 (Phase 6).
"""

import re
from collections import Counter

from src.logging_config import get_logger
from src.utils.validation import is_valid_text

logger = get_logger("viapharma.response_validator")


class TextValidator:
    """
    Text validation and cleaning for medical responses.

    Detects and filters garbage patterns, validates Bulgarian content,
    cleans English leaks, and ensures response quality.
    """

    # =========================================================================
    # GARBAGE PATTERNS - Filter low-quality text from responses
    # =========================================================================
    # These patterns detect text that shouldn't appear in user-facing responses:
    # - Drug leaflet boilerplate (side effects, contraindications)
    # - EU regulation fragments
    # - Translation artifacts and garbled text
    # - Medical jargon inappropriate for consumers
    # - Product catalog noise
    # - LLM hallucinations (Issue #17)

    _GARBAGE_PATTERNS = {
        # -----------------------------------------------------------------
        # DRUG LEAFLET / PACKAGE INSERT TEXT
        # -----------------------------------------------------------------
        # Side effects sections
        "нежелани реакции",
        "странични ефекти",
        "неизвестна честота",
        "с неизвестна честота",
        "нежелана реакция",
        "възможни нежелани",
        "side effects",
        "unknown frequency",
        "adverse reactions",
        "много чести",
        "чести нежелани",
        "нечести нежелани",
        "редки нежелани",
        # Anatomical system categories
        "мускулно- скелетната",
        "съединителната тъкан",
        "нарушения на кожата",
        "подкожната тъкан",
        "инфекции и ефекти",
        "мястото на приложение",
        "стомашно-чревни нарушения",
        "чернодробни нарушения",
        "сърдечни нарушения",
        "дихателни нарушения",
        "нарушения на нервната",
        "психични нарушения",
        "репродуктивни нарушения",
        "ендокринни нарушения",
        # Contraindications boilerplate
        "свръхчувствителност към активното",
        "свръхчувствителност към някоя от помощните",
        "противопоказания: свръхчувствителност",
        "да не се прилага при пациенти с",
        # Dosage/storage instructions
        "препоръчителна доза е",
        "максимална дневна доза",
        "да се съхранява на място",
        "срок на годност",
        "след изтичане на срока",
        "да се пази от деца",
        # Pharmaceutical body parts (leaflet language)
        "семенна течност",
        "сперматогенеза",
        "ерекция",
        # -----------------------------------------------------------------
        # EU REGULATIONS / LEGAL TEXT
        # -----------------------------------------------------------------
        "емисиите на парникови",
        "парникови газове",
        "регламент",
        "европейския парламент",
        "европейски парламент",
        "съвета",
        "в съответствие с изискванията",
        "директива на ес",
        "в съответствие с регламент",
        "официален вестник",
        "европейска комисия",
        "държави членки",
        "специални условия на труд",
        "стоманодобивната промишленост",
        "техниките средства за подпомагане",
        # EU Official Journal citations (ОВ = Официален вестник)
        "ов l",
        "ов c",
        "(ов l",
        "(ов c",
        "ов l 268",
        "ов l 269",
        "18.10.2003",
        "стр.",
        "стр)",
        "(стр.",
        "официален вестник на ес",
        "официален вестник на европейския съюз",
        "директива 2001/83/",
        "регламент (ео)",
        "регламент (ес)",
        # -----------------------------------------------------------------
        # REPEATED / INCOHERENT PHRASES
        # -----------------------------------------------------------------
        "болка в гърба, болка в гърба",
        "болка в корема, болка в корема",
        "главоболие, главоболие",
        "температура, температура",
        "не се препоръчва употребата",
        "да се каже, че",
        "консултирайте с вашия лекар или фармацевт",
        "този препарат",
        "лекарствен продукт",
        "човешки рекомбинантен човешки рекомбинантен",
        "рекомбинантен еритропоетин",
        "препоръчителни че",
        # -----------------------------------------------------------------
        # TRUNCATED / GARBLED TEXT
        # -----------------------------------------------------------------
        "(сърх)",
        "(Сърх)",
        "( сърх",
        "сърх)",
        "тол- сол",
        "сол- сол",
        "- сол-",
        "тол-сол",
        "( -",
        "- )",
        "( )",
        "(-)",
        "- -",
        "-- --",
        "---",
        "мои_____",
        "ст ст ст",
        "(д възможно най-",
        "таблетка на",
        "нетно вещество",
        "от с",
        "обучение",
        # -----------------------------------------------------------------
        # FRAGMENTS / NONSENSE / FILLER
        # -----------------------------------------------------------------
        "допринася за по-малко",
        "усили въздуха",
        "трябва да се вземат мерки",
        "както и да е, трябва",
        "както и да е",
        "в зависимост от състоянието",
        "да се избягва свързването",
        "по- малко от 6 месеца",
        "(по- малко от",
        "през последните три години",
        "cuts обикновено",
        # -----------------------------------------------------------------
        # IRRELEVANT CATEGORIES
        # -----------------------------------------------------------------
        "сметки и апарати",
        "зъбні протези",
        "грижа за зъбні протези",
        "трикотажни",
        "тарифен номер",
        "тарифна позиция",
        "митническа позиция",
        "стокова позиция",
        "лични данни",
        "защита на личните",
        "средство за защита",
        "репелент",
        "комар",
        "комари",
        "средство за комари",
        "защита срещу комари",
        "ще се справим ли",
        "уха си ти",
        # LLM hallucination patterns (Feb 2026 - Issue #17)
        "може да се използва като средство за",
        "за да може да се използва",
        "които могат да бъдат използвани като",
        # -----------------------------------------------------------------
        # MEDICAL JARGON (too technical for consumers)
        # -----------------------------------------------------------------
        "забрана за употреба при пациенти",
        "лекувани с човешки",
        "клинични изпитвания",
        "рандомизирано проучване",
        "двойно-сляпо",
        "плацебо-контролирано",
        "фармакокинетика",
        "фармакодинамика",
        "бионаличност",
        "полуживот на елиминиране",
        "плазмена концентрация",
        "пиково ниво",
        "лекарствени взаимодействия с",
        "индуктор на cyp",
        "инхибитор на cyp",
        "p-гликопротеин",
        # -----------------------------------------------------------------
        # PHARMACEUTICAL CODES / TECHNICAL
        # -----------------------------------------------------------------
        "mg/ml",
        "мг/мл",
        "таблетки x",
        "atc код",
        "atc-код",
        "анатомо-терапевтична",
        "inn:",
        "международно непатентно",
        "партиден номер",
        "сериен номер",
        # -----------------------------------------------------------------
        # TRANSLATION ARTIFACTS
        # -----------------------------------------------------------------
        "в в ",
        "на на ",
        "за за ",
        "от от ",
        "с с ",  # Doubled prepositions
        "the the",
        "a a ",
        "an an ",
        "is is ",  # English doubles
        " ,",
        " .",
        " ;",
        " :",  # Space before punctuation
        # -----------------------------------------------------------------
        # PRODUCT CATALOG / E-COMMERCE NOISE
        # -----------------------------------------------------------------
        "добави в количка",
        "добави в любими",
        "виж повече",
        "виж всички",
        "покажи повече",
        "изчерпано количество",
        "очаквайте скоро",
        "безплатна доставка",
        "бърза доставка",
        "цена с ддс",
        "цена без ддс",
        "% отстъпка",
        "артикулен номер",
        "баркод:",
        # -----------------------------------------------------------------
        # INSURANCE / ADMINISTRATIVE (Bulgarian healthcare system)
        # -----------------------------------------------------------------
        "нзок",
        "здравна каса",
        "реимбурсиране",
        "протокол за лечение",
        "позитивен списък",
        # -----------------------------------------------------------------
        # TRANSLATION HALLUCINATIONS / WRONG CONTEXT
        # -----------------------------------------------------------------
        # Completely wrong medical terms for context
        "introna",
        "интрон",
        "интерферон",
        "хепатит",
        "hepatitis",  # Unless actually asking about hepatitis
        "отстраняване на газовете",
        "отстраняване на газове",
        "цацове и слитове",
        "слитове за маса",
        "най-често се налага лечение с",
        "с intron",
        "с интрон",
        # Industrial/technical garbage
        "индустриален",
        "промишлен",
        "производство на",
        "преработка на",
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
        "_____",
        "____",
        "___",
        " ст ",
        " ст,",
        ",ст,",
        "ст ст",
        "мои___",
        "мои____",
        # English fragments that shouldn't appear in BG output
        "keep baby",
        "offer fluids",
        "lightly dressed",
        "keep бебе",
        "keep дете",  # Mixed English/BG
        "immediate care if fever",
        "immediate care if",
        "if fever exceeds",
        "if temperature exceeds",
        " if ",
        " exceeds ",  # English conjunctions in BG text
        "lukewarm",
        "sponge bath",
        "seek medical",
        "medical attention",
        # Common English words that indicate bad translation
        "keep ",
        "should ",
        "usually ",
        "avoid ",
        "monitor ",
        "ensure ",
        "apply ",
        " and ",
        "worsen after",
        "symptoms worsen",
        "see doctor",
        "consult doctor",
        # Malformed text patterns
        "това е в.",
        "това е в,",
        "в. or",
        ", or ",
        "крайни нарушения",
        "нарушения на вкуса",
        "ставите инфекции",
        "инфекции, които",
        '" вижте',
        '["',
        '"]',
        # Numbers with spaces in wrong places
        "38 . 5",
        "38. 5",
    }

    # Garbage patterns for self-care tips (LLM/translation artifacts)
    _TIP_GARBAGE = (
        "стъпления",
        "заявление за одобряване",
        "субекти които не са",
        "сребрист пръстен",
        "гимназиален",
        "направено е от лекар",
        "допълнение на външната",
        "допълнение на вътрешни",
        "корекция на дозата",
        "препарат за дългосрочна",
        "белезникав",
        "хранителна добавка за",
        "приложете повече от една доза веднъж на всеки две седмици",
        "сметки на бюджетите",
        "това е всичко което",
        # LLM hallucination patterns (Issue #17)
        "зъбні протези",
        "зъбни протези",
        "грижа за зъбні протези",
        "защита на личните",
        "средство за защита",
        "репелент",
        "комар",
        "комари",
        "пластмасов",
        "ламарин",
        "металокерамика",
        "отпадъчни препарати",
    )

    # Valid self-care keywords — tip should have at least one
    _VALID_TIP_KEYWORDS = (
        "течност",
        "вода",
        "почивка",
        "почивайте",
        "компрес",
        "храна",
        "сън",
        "витамин",
        "солен",
        "гаргар",
        "топл",
        "студен",
        "въздух",
        "влажност",
        "хидратаци",
        "масаж",
        "дишане",
        "избягвайте",
        "проверете",
        "облечете",
        "давайте",
        "пийте",
        "яжте",
        "отдих",
        "отпочин",
        "намалете",
        "приложете",
        "бебе",
        "дете",
        "грижа",
        "листовка",
        "доза",
        "възстановяване",
    )

    def __init__(self, translator=None):
        """
        Initialize TextValidator.

        Args:
            translator: Optional translator instance for re-translation of English leaks
        """
        self.translator = translator

    def contains_garbage(self, text: str) -> bool:
        """
        Check if text contains garbage patterns, low Bulgarian content, or excessive repetition.

        Args:
            text: Text to validate

        Returns:
            True if text contains garbage, False otherwise
        """
        if not is_valid_text(text, min_length=3):
            return True

        text_lower = text.lower()

        # Check for garbage patterns
        if any(pattern in text_lower for pattern in self._GARBAGE_PATTERNS):
            return True

        # Check Bulgarian content ratio (target 95%+ per Issue 6, filter if below 65%)
        bg_ratio = self.calculate_bulgarian_ratio(text)
        if bg_ratio < 0.65:  # Less than 65% Bulgarian = garbage for BG output
            return True

        # Check for model output artifacts (word/word/word patterns, repeated substrings)
        artifact_patterns = [
            r"\w+/\s*\w+/\s*\w+",  # word/word/word patterns like "си гол/ си гол/ си гол"
            r"(.{2,10})\1{2,}",  # repeated substrings 2+ times
        ]
        for pattern in artifact_patterns:
            if re.search(pattern, text_lower):
                return True

        # Check for excessive word repetition
        words = text_lower.split()
        if len(words) >= 5:
            word_counts = Counter(words)
            # If any word appears more than 50% of the time, it's garbage
            max_count = max(word_counts.values())
            if max_count > len(words) * 0.5:
                return True

        # Check for 2-word phrase repetition (catches patterns like "си гол си гол")
        if len(words) >= 4:
            for i in range(len(words) - 1):
                phrase = " ".join(words[i : i + 2])
                if len(phrase) > 3 and text_lower.count(phrase) >= 2:
                    return True

        # Check for 3-word phrase repetition
        if len(words) > 10:
            for i in range(len(words) - 5):
                phrase = " ".join(words[i : i + 3])
                if text_lower.count(phrase) >= 3:
                    return True

        return False

    def filter_garbage_sentences(self, text: str) -> str:
        """
        Remove garbage sentences from text. Keeps only coherent parts.

        Args:
            text: Text to filter

        Returns:
            Filtered text with garbage sentences removed
        """
        if not is_valid_text(text, min_length=5):
            return ""

        # Split by sentence-ending punctuation
        sentences = re.split(r"(?<=[.!?])\s+", text)
        kept = []

        for s in sentences:
            s = s.strip()
            if not s or len(s) < 10:
                continue

            # If a "sentence" is very long and contains comma, check each clause
            if len(s) > 120 and "," in s:
                clauses = [c.strip() for c in s.split(",") if len(c.strip()) >= 10]
                for c in clauses:
                    if not self.contains_garbage(c):
                        upper = sum(1 for ch in c if ch.isupper())
                        if len(c) > 0 and upper / len(c) <= 0.4:
                            kept.append(c)
                continue

            if self.contains_garbage(s):
                continue

            # Drop sentences that are mostly uppercase (EU jargon)
            upper = sum(1 for c in s if c.isupper())
            if len(s) > 0 and upper / len(s) > 0.4:
                continue

            kept.append(s)

        result = " ".join(kept) if kept else ""

        # Fallback: if critical garbage still present, truncate before that sentence
        critical = [
            "защита на личните",
            "лични данни",
            "средство за защита",
            "зъбні протези",
            "зъбни протези",
            "металокерамика",
        ]
        for phrase in critical:
            if phrase in result.lower():
                idx = result.lower().index(phrase)
                # Find last sentence end before the garbage
                before = result[:idx]
                last_end = max(before.rfind(". "), before.rfind("! "), before.rfind("? "))
                result = (result[: last_end + 1].rstrip() if last_end >= 0 else "") or ""
                break

        return result

    def calculate_bulgarian_ratio(self, text: str) -> float:
        """
        Calculate the ratio of Bulgarian characters in text.

        Args:
            text: Text to analyze

        Returns:
            Ratio of Bulgarian characters (0.0 to 1.0)
        """
        if not text:
            return 0.0

        bulgarian_chars = set("абвгдежзийклмнопрстуфхцчшщъьюя")
        text_lower = text.lower()
        bg_count = sum(1 for c in text_lower if c in bulgarian_chars)
        total_alpha = sum(1 for c in text_lower if c.isalpha())

        return bg_count / total_alpha if total_alpha > 0 else 0.0

    def is_valid_self_care_tip(self, tip: str) -> bool:
        """
        Filter garbage self-care tips from LLM/translation output.

        Args:
            tip: Self-care tip text

        Returns:
            True if tip is valid, False if garbage
        """
        if not is_valid_text(tip, min_length=8):
            return False

        t = tip.lower().strip()

        # Reject known garbage
        if any(g in t for g in self._TIP_GARBAGE):
            return False

        # Reject >50% uppercase (garbled)
        upper = sum(1 for c in tip if c.isupper())
        if len(tip) > 0 and upper / len(tip) > 0.5:
            return False

        # Reject if no health-related keyword
        if not any(kw in t for kw in self._VALID_TIP_KEYWORDS):
            return False

        return True

    def clean_english_leaks(self, text: str) -> str:
        """
        Remove English words leaked into otherwise-Bulgarian text.

        Strategy: identify sentences with English words and re-translate
        the entire sentence (not individual words, which produces garbage).
        Drop sentences that can't be translated.

        Args:
            text: Text to clean

        Returns:
            Cleaned text with English leaks removed
        """
        if not text or self.calculate_bulgarian_ratio(text) >= 0.95:
            return text  # Already clean Bulgarian

        if self.calculate_bulgarian_ratio(text) < 0.50:
            return text  # Too much English — not a "leak" scenario

        # Split into sentences and clean each
        sentences = re.split(r"(?<=[.!?])\s+", text)

        if len(sentences) <= 1:
            # Single sentence: check for English words
            latin_words = re.findall(r"\b[a-zA-Z]{3,}\b", text)

            # Known OK words (medical terms, units, brands that can stay in English)
            known_ok_lower = {
                # Standard medical terms / abbreviations
                "covid", "sars", "otc", "nsaid",
                "paracetamol", "ibuprofen", "aspirin", "diclofenac",
                # Units and dilutions
                "mg", "ml", "ph", "dh", "ch",
                # Major brands
                "nurofen", "brufen", "voltaren", "advil", "tylenol",
                "claritine", "zyrtec", "boiron", "tantum", "motilium",
            }

            # English words to clean (Issue #19: include capitalized medical terms)
            eng_words = [
                w for w in latin_words
                if w.lower() not in known_ok_lower
            ]

            if eng_words and self.translator:
                # Re-translate the entire sentence
                fresh = self.translator.translate_to_bulgarian(text)
                if fresh and self.calculate_bulgarian_ratio(fresh) >= 0.85:
                    # Check for repetition garbage
                    if not self.has_repetition(fresh):
                        return fresh

                # If translation failed or produced garbage, just remove English words
                result = text
                for w in eng_words:
                    result = result.replace(w, "").replace("  ", " ")
                return result.strip()

            return text

        # Multiple sentences: clean each independently
        clean = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            if self.calculate_bulgarian_ratio(sent) >= 0.90:
                clean.append(sent)
            elif self.translator:
                # Try to re-translate
                fresh = self.translator.translate_to_bulgarian(sent)
                if fresh and self.calculate_bulgarian_ratio(fresh) >= 0.80 and not self.has_repetition(fresh):
                    clean.append(fresh)
                # Otherwise drop the sentence

        return " ".join(clean) if clean else text

    @staticmethod
    def has_repetition(text: str, threshold: int = 3) -> bool:
        """
        Detect translation garbage — repeated words/phrases.

        Args:
            text: Text to check
            threshold: Maximum allowed repetitions

        Returns:
            True if excessive repetition detected
        """
        words = text.lower().split()
        if len(words) < 4:
            return False

        # Check for word repetition (same word appearing > threshold times)
        counts = Counter(words)
        return any(c >= threshold for w, c in counts.items() if len(w) > 2)


# Singleton instance for backward compatibility
_text_validator: TextValidator | None = None


def get_text_validator(translator=None) -> TextValidator:
    """Get or create the TextValidator instance."""
    global _text_validator
    if _text_validator is None:
        _text_validator = TextValidator(translator=translator)
    return _text_validator
