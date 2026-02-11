"""
Translation module for Bulgarian ↔ English using MarianMT.

Uses Helsinki-NLP's MarianMT models:
- BG → EN: Helsinki-NLP/opus-mt-bg-en
- EN → BG: Helsinki-NLP/opus-mt-en-bg
"""

from typing import Optional
from functools import lru_cache

from transformers import MarianMTModel, MarianTokenizer


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

        # Cache for frequent translations
        self._cache_bg_to_en = {}
        self._cache_en_to_bg = {}
        self._cache_max_size = 1000

    def _load_bg_to_en(self) -> None:
        """Load the Bulgarian to English model."""
        if self._bg_to_en_model is None:
            print(f"Loading translation model: {self.BG_TO_EN_MODEL}...")
            self._bg_to_en_tokenizer = MarianTokenizer.from_pretrained(self.BG_TO_EN_MODEL)
            self._bg_to_en_model = MarianMTModel.from_pretrained(self.BG_TO_EN_MODEL)
            print("BG→EN model loaded!")

    def _load_en_to_bg(self) -> None:
        """Load the English to Bulgarian model."""
        if self._en_to_bg_model is None:
            print(f"Loading translation model: {self.EN_TO_BG_MODEL}...")
            self._en_to_bg_tokenizer = MarianTokenizer.from_pretrained(self.EN_TO_BG_MODEL)
            self._en_to_bg_model = MarianMTModel.from_pretrained(self.EN_TO_BG_MODEL)
            print("EN→BG model loaded!")

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
        if text in self._cache_bg_to_en:
            return self._cache_bg_to_en[text]

        # Load model if needed
        self._load_bg_to_en()

        # Tokenize and translate
        inputs = self._bg_to_en_tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        translated = self._bg_to_en_model.generate(**inputs)
        result = self._bg_to_en_tokenizer.decode(translated[0], skip_special_tokens=True)

        # Cache result
        if len(self._cache_bg_to_en) < self._cache_max_size:
            self._cache_bg_to_en[text] = result

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
        if text in self._cache_en_to_bg:
            return self._cache_en_to_bg[text]

        # Load model if needed
        self._load_en_to_bg()

        # Tokenize and translate
        inputs = self._en_to_bg_tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        translated = self._en_to_bg_model.generate(**inputs)
        result = self._en_to_bg_tokenizer.decode(translated[0], skip_special_tokens=True)

        # Cache result
        if len(self._cache_en_to_bg) < self._cache_max_size:
            self._cache_en_to_bg[text] = result

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


# Global translator instance (lazy loaded)
_translator: Optional[Translator] = None


def get_translator() -> Translator:
    """Get or create the global translator instance."""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator
