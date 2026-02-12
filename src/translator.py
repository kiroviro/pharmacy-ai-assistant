"""
Translation module for Bulgarian ↔ English using MarianMT.

Uses Helsinki-NLP's MarianMT models:
- BG → EN: Helsinki-NLP/opus-mt-bg-en
- EN → BG: Helsinki-NLP/opus-mt-en-bg
"""

from collections import OrderedDict
from typing import Optional

from transformers import MarianMTModel, MarianTokenizer

from src.logging_config import get_logger
from src.config import get_settings

logger = get_logger("viapharma.translator")


class LRUCache:
    """
    Simple LRU (Least Recently Used) cache implementation.

    Evicts the oldest entries when the cache reaches max_size.
    """

    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[str]:
        """Get a value from cache, moving it to end (most recently used)."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, value: str) -> None:
        """Set a value in cache, evicting oldest if necessary."""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                # Evict oldest (first) item
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug(f"Cache evicted entry", extra={"evicted_key_len": len(evicted_key)})
        self._cache[key] = value

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 1)
        }


class Translator:
    """
    Handles translation between Bulgarian and English.

    Uses MarianMT models from Helsinki-NLP for high-quality translation.
    Models are lazy-loaded on first use to reduce startup time.
    """

    # Model identifiers
    BG_TO_EN_MODEL = "Helsinki-NLP/opus-mt-bg-en"
    EN_TO_BG_MODEL = "Helsinki-NLP/opus-mt-en-bg"

    def __init__(self):
        """Initialize the translator (models loaded lazily)."""
        self._bg_to_en_model = None
        self._bg_to_en_tokenizer = None
        self._en_to_bg_model = None
        self._en_to_bg_tokenizer = None

        # LRU cache for frequent translations
        settings = get_settings()
        cache_size = settings.translation_cache_size
        self._cache_bg_to_en = LRUCache(max_size=cache_size)
        self._cache_en_to_bg = LRUCache(max_size=cache_size)

    def _load_bg_to_en(self) -> None:
        """Load the Bulgarian to English model."""
        if self._bg_to_en_model is None:
            logger.info(f"Loading translation model: {self.BG_TO_EN_MODEL}...")
            self._bg_to_en_tokenizer = MarianTokenizer.from_pretrained(self.BG_TO_EN_MODEL)
            self._bg_to_en_model = MarianMTModel.from_pretrained(self.BG_TO_EN_MODEL)
            logger.info("BG→EN model loaded!")

    def _load_en_to_bg(self) -> None:
        """Load the English to Bulgarian model."""
        if self._en_to_bg_model is None:
            logger.info(f"Loading translation model: {self.EN_TO_BG_MODEL}...")
            self._en_to_bg_tokenizer = MarianTokenizer.from_pretrained(self.EN_TO_BG_MODEL)
            self._en_to_bg_model = MarianMTModel.from_pretrained(self.EN_TO_BG_MODEL)
            logger.info("EN→BG model loaded!")

    def load_all(self) -> None:
        """Pre-load both translation models."""
        self._load_bg_to_en()
        self._load_en_to_bg()

    def translate_to_english(self, text: str) -> str:
        """
        Translate Bulgarian text to English.

        Args:
            text: Bulgarian text to translate

        Returns:
            English translation
        """
        if not text or not text.strip():
            return text

        # Check cache
        cached = self._cache_bg_to_en.get(text)
        if cached is not None:
            return cached

        # Load model if needed
        self._load_bg_to_en()

        # Tokenize and translate
        inputs = self._bg_to_en_tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        translated = self._bg_to_en_model.generate(**inputs)
        result = self._bg_to_en_tokenizer.decode(translated[0], skip_special_tokens=True)

        # Cache result
        self._cache_bg_to_en.set(text, result)

        return result

    # Common medical terms that often fail to translate
    _MEDICAL_TERM_TRANSLATIONS = {
        # Symptoms
        "viral infection": "вирусна инфекция",
        "bacterial infection": "бактериална инфекция",
        "sore throat": "болки в гърлото",
        "headache": "главоболие",
        "fever": "температура",
        "cough": "кашлица",
        "runny nose": "хрема",
        "cold": "настинка",
        "flu": "грип",
        "pain": "болка",
        "inflammation": "възпаление",
        "allergy": "алергия",
        "dizziness": "световъртеж",
        "fatigue": "умора",
        "nausea": "гадене",
        "vomiting": "повръщане",
        "diarrhea": "диария",
        "constipation": "запек",
        "rash": "обрив",
        "swelling": "подуване",
        "itching": "сърбеж",
        "tension headache": "тензионно главоболие",
        "tension or stress": "напрежение или стрес",
        "stress": "стрес",
        "tension": "напрежение",
        "migraine": "мигрена",
        "muscle pain": "мускулна болка",
        "back pain": "болки в гърба",
        "stomach pain": "стомашна болка",
        "abdominal pain": "коремна болка",
        "ear pain": "болка в ухото",
        "chest pain": "болка в гърдите",
        "joint pain": "болка в ставите",
        # Causes
        "poor posture": "лоша стойка",
        "dehydration": "дехидратация",
        "lack of sleep": "липса на сън",
        "eye strain": "напрежение на очите",
        # Treatments
        "analgesics": "болкоуспокояващи",
        "antipyretics": "антипиретици",
        "anti-inflammatory": "противовъзпалително",
        "decongestant": "деконгестант",
        "antihistamine": "антихистамин",
        "pain relievers": "болкоуспокояващи",
        "painkiller": "болкоуспокояващо",
        "painkillers": "болкоуспокояващи",
        # Self-care phrases
        "drink plenty of fluids": "пийте много течности",
        "stay hydrated": "пийте достатъчно течности",
        "get plenty of rest": "почивайте достатъчно",
        "rest in a quiet room": "почивайте в тиха стая",
        "apply cold compress": "приложете студен компрес",
        "apply warm compress": "приложете топъл компрес",
        "avoid bright lights": "избягвайте ярка светлина",
        "reduce screen time": "намалете времето пред екран",
        "rest": "почивка",
        # Doctor recommendations
        "see doctor": "посетете лекар",
        "see a doctor": "посетете лекар",
        "consult a doctor": "консултирайте се с лекар",
        "consult your doctor": "консултирайте се с лекар",
        "seek medical help": "потърсете медицинска помощ",
        "seek help": "потърсете помощ",
        "seek immediate help": "потърсете незабавна помощ",
        "if symptoms persist": "ако симптомите продължават",
        "if symptoms worsen": "ако симптомите се влошат",
        "with fever": "с температура",
        "stiff neck": "скован врат",
        "with fever or stiff neck": "с температура или скован врат",
        # Recovery
        "usually resolves": "обикновено преминава",
        "within a few hours": "в рамките на няколко часа",
        "within 24 hours": "в рамките на 24 часа",
        "within 2-4 hours": "в рамките на 2-4 часа",
        "symptoms": "симптоми",
        "treatment": "лечение",
        "self-care": "домашни грижи",
        "recovery": "възстановяване",
        # Common phrases
        "tension headaches occur when": "тензионното главоболие се появява когато",
        "muscles in head and neck tighten": "мускулите на главата и врата се стягат",
        "often from stress": "често от стрес",
    }

    def _calculate_bulgarian_ratio(self, text: str) -> float:
        """Calculate the ratio of Bulgarian characters in text."""
        if not text:
            return 0.0
        bulgarian_chars = set("абвгдежзийклмнопрстуфхцчшщъьюя")
        text_lower = text.lower()
        bg_count = sum(1 for c in text_lower if c in bulgarian_chars)
        total_alpha = sum(1 for c in text_lower if c.isalpha())
        return bg_count / total_alpha if total_alpha > 0 else 0.0

    def _apply_medical_dictionary(self, text: str) -> str:
        """Replace common English medical terms with Bulgarian translations."""
        result = text
        for eng, bg in self._MEDICAL_TERM_TRANSLATIONS.items():
            # Case-insensitive replacement
            import re
            result = re.sub(re.escape(eng), bg, result, flags=re.IGNORECASE)
        return result

    def translate_to_bulgarian(self, text: str) -> str:
        """
        Translate English text to Bulgarian.

        Args:
            text: English text to translate

        Returns:
            Bulgarian translation
        """
        if not text or not text.strip():
            return text

        # Check cache
        cached = self._cache_en_to_bg.get(text)
        if cached is not None:
            return cached

        # Load model if needed
        self._load_en_to_bg()

        # Tokenize and translate
        inputs = self._en_to_bg_tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        translated = self._en_to_bg_model.generate(**inputs)
        result = self._en_to_bg_tokenizer.decode(translated[0], skip_special_tokens=True)

        # Check Bulgarian ratio and try fallback if too low
        bg_ratio = self._calculate_bulgarian_ratio(result)
        if bg_ratio < 0.6:
            # Try applying medical dictionary first
            result_with_dict = self._apply_medical_dictionary(result)
            new_ratio = self._calculate_bulgarian_ratio(result_with_dict)

            if new_ratio > bg_ratio:
                result = result_with_dict
                bg_ratio = new_ratio

            # If still low, try sentence-by-sentence translation
            if bg_ratio < 0.6 and '.' in text:
                sentences = [s.strip() for s in text.split('.') if s.strip()]
                if len(sentences) > 1:
                    translated_sentences = []
                    for sentence in sentences:
                        inputs = self._en_to_bg_tokenizer(
                            sentence, return_tensors="pt", padding=True, truncation=True, max_length=512
                        )
                        trans = self._en_to_bg_model.generate(**inputs)
                        trans_text = self._en_to_bg_tokenizer.decode(trans[0], skip_special_tokens=True)
                        # Apply dictionary to each sentence
                        trans_text = self._apply_medical_dictionary(trans_text)
                        translated_sentences.append(trans_text)
                    sentence_result = '. '.join(translated_sentences)
                    if self._calculate_bulgarian_ratio(sentence_result) > bg_ratio:
                        result = sentence_result

        # Cache result
        self._cache_en_to_bg.set(text, result)

        return result

    def translate_batch_to_english(self, texts: list[str]) -> list[str]:
        """
        Translate multiple Bulgarian texts to English (more efficient).

        Args:
            texts: List of Bulgarian texts

        Returns:
            List of English translations
        """
        if not texts:
            return []

        self._load_bg_to_en()

        # Filter out empty strings and track positions
        non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        if not non_empty:
            return texts

        # Translate non-empty texts
        indices, valid_texts = zip(*non_empty)
        inputs = self._bg_to_en_tokenizer(
            list(valid_texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512
        )
        translated = self._bg_to_en_model.generate(**inputs)
        results = [self._bg_to_en_tokenizer.decode(t, skip_special_tokens=True) for t in translated]

        # Reconstruct full list
        output = list(texts)
        for idx, result in zip(indices, results):
            output[idx] = result

        return output

    def translate_batch_to_bulgarian(self, texts: list[str]) -> list[str]:
        """
        Translate multiple English texts to Bulgarian (more efficient).

        Args:
            texts: List of English texts

        Returns:
            List of Bulgarian translations
        """
        if not texts:
            return []

        self._load_en_to_bg()

        # Filter out empty strings and track positions
        non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        if not non_empty:
            return texts

        # Translate non-empty texts
        indices, valid_texts = zip(*non_empty)
        inputs = self._en_to_bg_tokenizer(
            list(valid_texts),
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512
        )
        translated = self._en_to_bg_model.generate(**inputs)
        results = [self._en_to_bg_tokenizer.decode(t, skip_special_tokens=True) for t in translated]

        # Reconstruct full list
        output = list(texts)
        for idx, result in zip(indices, results):
            output[idx] = result

        return output

    def clear_cache(self) -> None:
        """Clear the translation cache."""
        self._cache_bg_to_en.clear()
        self._cache_en_to_bg.clear()
        logger.info("Translation caches cleared")

    def get_cache_stats(self) -> dict:
        """Get cache statistics for monitoring."""
        return {
            "bg_to_en": self._cache_bg_to_en.stats,
            "en_to_bg": self._cache_en_to_bg.stats
        }


# Global translator instance (lazy loaded)
_translator: Optional[Translator] = None


def get_translator() -> Translator:
    """Get or create the global translator instance."""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator
