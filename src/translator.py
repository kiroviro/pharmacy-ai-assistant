"""
Translation module for English → Bulgarian using MarianMT.

Uses Helsinki-NLP's MarianMT model: Helsinki-NLP/opus-mt-en-bg

This module handles:
- Response translation (EN→BG) for medical advice text
- Product description translation
- Medical term dictionary for common translations

Query translation (BG→EN) is handled by the unified processor.
"""

from collections import OrderedDict

from transformers import MarianMTModel, MarianTokenizer

from src.config import get_settings
from src.logging_config import get_logger
from src.utils.validation import is_empty_or_whitespace

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

    def get(self, key: str) -> str | None:
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
                logger.debug("Cache evicted entry", extra={"evicted_key_len": len(evicted_key)})
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
            "hit_rate_percent": round(hit_rate, 1),
        }


class Translator:
    """
    Handles translation between Bulgarian and English.

    Uses MarianMT models from Helsinki-NLP for high-quality translation.
    Models are lazy-loaded on first use to reduce startup time.
    """

    # Model identifiers
    EN_TO_BG_MODEL = "Helsinki-NLP/opus-mt-en-bg"

    def __init__(self):
        """Initialize the translator (models loaded lazily)."""
        self._en_to_bg_model = None
        self._en_to_bg_tokenizer = None

        # LRU cache for frequent translations
        settings = get_settings()
        cache_size = settings.translation_cache_size
        self._cache_en_to_bg = LRUCache(max_size=cache_size)

    def _load_en_to_bg(self) -> None:
        """Load the English to Bulgarian model."""
        if self._en_to_bg_model is None:
            logger.info(f"Loading translation model: {self.EN_TO_BG_MODEL}...")
            self._en_to_bg_tokenizer = MarianTokenizer.from_pretrained(self.EN_TO_BG_MODEL)
            self._en_to_bg_model = MarianMTModel.from_pretrained(self.EN_TO_BG_MODEL)
            logger.info("EN→BG model loaded!")

    def load_all(self) -> None:
        """Pre-load the EN→BG translation model."""
        self._load_en_to_bg()

    # Common medical terms that often fail to translate
    _MEDICAL_TERM_TRANSLATIONS = {
        # Symptoms (plural first for correct matching)
        "viral upper respiratory infection": "вирусна инфекция на горните дихателни пътища",
        "upper respiratory infection": "инфекция на горните дихателни пътища",
        "respiratory infection": "респираторна инфекция",
        "viral infection": "вирусна инфекция",
        "bacterial infection": "бактериална инфекция",
        "viral": "вирусна",
        "bacterial": "бактериална",
        "uri": "инфекция на горните дихателни пътища",
        "sore throat": "болки в гърлото",
        "headaches": "главоболия",
        "headache": "главоболие",
        "fevers": "температури",
        "fever": "температура",
        "high fever": "висока температура",
        "cough": "кашлица",
        "runny nose": "хрема",
        "sniffles": "хрема",
        "sneezing": "кихане",
        "bronchitis": "бронхит",
        "cold": "настинка",
        "common cold": "настинка",
        "flu": "грип",
        "influenza": "грип",
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
        "teething": "никнене на зъби",
        # Mouth/oral conditions (Issue #19 - fix English leaks)
        "afts": "афти",
        "aphthous ulcers": "афтозни язви",
        "mouth ulcers": "язви в устата",
        "canker sores": "афти",
        "gingivitis": "гингивит",
        "gums": "венци",
        "inflamed gums": "възпалени венци",
        "teething pain": "болка при никнене на зъби",
        # Infant/Baby related
        "infant": "бебе",
        "infants": "бебета",
        "baby": "бебе",
        "babies": "бебета",
        "newborn": "новородено",
        "newborns": "новородени",
        "child": "дете",
        "children": "деца",
        "toddler": "малко дете",
        "pediatric": "детски",
        "infant fever": "температура при бебе",
        "baby fever": "температура при бебе",
        "6 month old": "6-месечно",
        "6 months old": "на 6 месеца",
        "months old": "месеца",
        "years old": "години",
        # Causes
        "poor posture": "лоша стойка",
        "dehydration": "дехидратация",
        "lack of sleep": "липса на сън",
        "eye strain": "напрежение на очите",
        # Treatments
        "analgesics": "болкоуспокояващи",
        "antipyretics": "антипиретици (за сваляне на температура)",
        "antipyretic": "антипиретик (за температура)",
        "antipyretics and throat lozenges": "антипиретици и таблетки за гърло",
        "antipyretics and expectorants": "антипиретици и отхрачващи средства",
        "anti-inflammatory": "противовъзпалително",
        "decongestant": "деконгестант (за запушен нос)",
        "decongestants": "деконгестанти (за запушен нос)",
        "antihistamine": "антихистамин",
        "antihistamines": "антихистамини",
        "expectorant": "отхрачващо средство",
        "expectorants": "отхрачващи средства",
        "cough suppressant": "средство за потискане на кашлицата",
        "cough medicine": "лекарство за кашлица",
        "throat lozenges": "таблетки за гърло",
        "lozenges": "таблетки за смучене",
        "pain relievers": "болкоуспокояващи",
        "painkiller": "болкоуспокояващо",
        "painkillers": "болкоуспокояващи",
        "fever reducer": "лекарство за сваляне на температура",
        "fever reducers": "лекарства за сваляне на температура",
        "acetaminophen": "парацетамол",
        "paracetamol": "парацетамол",
        "ibuprofen": "ибупрофен",
        "nasal spray": "спрей за нос",
        "nasal drops": "капки за нос",
        "antivirals": "антивирусни средства",
        "antiviral": "антивирусно средство",
        "antibiotics": "антибиотици",
        "antibiotic": "антибиотик",
        # Self-care phrases
        "drink plenty of fluids": "пийте много течности",
        "stay hydrated": "пийте достатъчно течности",
        "get plenty of rest": "почивайте достатъчно",
        "rest in a quiet room": "почивайте в тиха стая",
        "rest in quiet room": "почивайте в тиха стая",
        "apply cold compress": "приложете студен компрес",
        "apply warm compress": "приложете топъл компрес",
        "cold compress": "студен компрес",
        "warm compress": "топъл компрес",
        "avoid bright lights": "избягвайте ярка светлина",
        "reduce screen time": "намалете времето пред екран",
        "rest": "почивка",
        "elevate head": "повдигнете главата",
        "keep hydrated": "поддържайте хидратация",
        "gargle with salt water": "гаргара със солена вода",
        "use humidifier": "използвайте овлажнител",
        "avoid caffeine": "избягвайте кофеин",
        "avoid alcohol": "избягвайте алкохол",
        "take breaks": "правете почивки",
        "gentle massage": "лек масаж",
        # Baby/infant self-care
        "keep baby lightly dressed": "облечете бебето леко",
        "keep the baby lightly dressed": "облечете бебето леко",
        "dress baby lightly": "облечете бебето леко",
        "dress lightly": "облечете леко",
        "lightly dressed": "облечете леко",
        "offer fluids frequently": "давайте течности често",
        "offer fluids often": "давайте течности често",
        "offer fluids": "давайте течности",
        "offer plenty of fluids": "давайте много течности",
        "give fluids": "давайте течности",
        "monitor temperature": "следете температурата",
        "monitor the temperature": "следете температурата",
        "check temperature regularly": "проверявайте температурата редовно",
        "lukewarm bath": "хладка вана",
        "cool bath": "хладка вана",
        "sponge bath": "разтриване с мокра кърпа",
        "cool compress on forehead": "хладен компрес на челото",
        "cool compress": "хладен компрес",
        "breastfeed frequently": "кърмете често",
        "breastfeed often": "кърмете често",
        "keep room cool": "поддържайте стаята хладна",
        "keep the room cool": "поддържайте стаята хладна",
        "ensure adequate rest": "осигурете достатъчна почивка",
        "adequate rest": "достатъчна почивка",
        "plenty of rest": "достатъчна почивка",
        # Doctor recommendations
        "see doctor": "посетете лекар",
        "see a doctor": "посетете лекар",
        "see a pediatrician": "посетете педиатър",
        "consult a doctor": "консултирайте се с лекар",
        "consult your doctor": "консултирайте се с лекар",
        "consult a pediatrician": "консултирайте се с педиатър",
        "seek medical help": "потърсете медицинска помощ",
        "seek medical attention": "потърсете медицинска помощ",
        "seek help": "потърсете помощ",
        "seek immediate help": "потърсете незабавна помощ",
        "seek immediate medical attention": "потърсете незабавна медицинска помощ",
        "if symptoms persist": "ако симптомите продължават",
        "if symptoms worsen": "ако симптомите се влошат",
        "if fever persists": "ако температурата продължава",
        "if fever exceeds": "ако температурата надвиши",
        "with fever": "с температура",
        "stiff neck": "скован врат",
        "with fever or stiff neck": "с температура или скован врат",
        "immediate care": "незабавна грижа",
        "emergency care": "спешна помощ",
        # Recovery
        "usually resolves": "обикновено преминава",
        "typically resolves": "обикновено преминава",
        "within a few hours": "в рамките на няколко часа",
        "within 24 hours": "в рамките на 24 часа",
        "within 2-4 hours": "в рамките на 2-4 часа",
        "within 2-3 days": "в рамките на 2-3 дни",
        "within 3-5 days": "в рамките на 3-5 дни",
        "symptoms": "симптоми",
        "treatment": "лечение",
        "self-care": "домашни грижи",
        "home care": "домашни грижи",
        "recovery": "възстановяване",
        "most viral fevers": "повечето вирусни температури",
        "viral fevers": "вирусни температури",
        # Common phrases - full sentences for better translation
        "tension headaches occur when": "тензионното главоболие се появява когато",
        "muscles in head and neck tighten": "мускулите на главата и врата се стягат",
        "often from stress": "често от стрес",
        "often from stress or poor posture": "често от стрес или лоша стойка",
        "occur when": "се появява когато",
        "from stress or": "от стрес или",
        "or poor posture": "или лоша стойка",
        # Common explanations - full phrases
        "tension headaches occur when muscles in head and neck tighten, often from stress or poor posture": "Тензионното главоболие се появява, когато мускулите на главата и врата се стягат, често от стрес или лоша стойка",
        "analgesics block pain signals and reduce inflammation, providing relief within 30-60 minutes": "Болкоуспокояващите блокират болковите сигнали и намаляват възпалението, като осигуряват облекчение в рамките на 30-60 минути",
        "block pain signals": "блокират болковите сигнали",
        "reduce inflammation": "намаляват възпалението",
        "providing relief": "осигурявайки облекчение",
        "within 30-60 minutes": "в рамките на 30-60 минути",
        # Recovery phrases
        "most headaches improve": "повечето главоболия се подобряват",
        "most headaches improve within 2-4 hours with treatment": "Повечето главоболия се подобряват в рамките на 2-4 часа с лечение",
        "improve within": "се подобряват в рамките на",
        "with treatment": "с лечение",
        "with rest and treatment": "с почивка и лечение",
        # Warning phrases
        "see doctor if severe or persistent": "посетете лекар ако е силно или продължително",
        "if severe or persistent": "ако е силно или продължително",
        "see doctor if persists beyond": "посетете лекар ако продължава повече от",
        "if persists beyond": "ако продължава повече от",
        "if persists": "ако продължава",
        "if worsens": "ако се влоши",
        "if persists beyond 3 days": "ако продължава повече от 3 дни",
        "severe": "силно",
        "persistent": "продължително",
        "seek medical help if": "потърсете медицинска помощ ако",
        "consult your doctor if needed": "консултирайте се с Вашия лекар при нужда",
        "consult your doctor if necessary": "консултирайте се с Вашия лекар ако е необходимо",
        "if needed": "при нужда",
        "if necessary": "ако е необходимо",
        # Common connecting words
        " and ": " и ",
        " or ": " или ",
        " with ": " с ",
        " in ": " в ",
        " for ": " за ",
        " to ": " за ",
        " from ": " от ",
        " of ": " на ",
        " is ": " е ",
        " are ": " са ",
        " the ": " ",
        " a ": " ",
        "in 30-60 minutes": "в рамките на 30-60 минути",
        "30-60 minutes": "30-60 минути",
        "minutes": "минути",
        "hours": "часа",
        "days": "дни",
        "weeks": "седмици",
        # More common words
        "possibly": "възможно",
        "typically": "обикновено",
        "usually": "обикновено",
        "often": "често",
        "sometimes": "понякога",
        "may": "може",
        "might": "може",
        "can": "може",
        "should": "трябва",
        "will": "ще",
        "caused by": "причинено от",
        "due to": "поради",
        "because of": "поради",
        "upper respiratory tract infection": "инфекция на горните дихателни пътища",
        "rhinoviruses": "риновируси",
        "rhinovirus": "риновирус",
        "persist beyond": "продължат повече от",
        "persist": "продължават",
        "difficulty breathing": "затруднено дишане",
        "shorten the duration": "скъсят продължителността",
        "duration": "продължителност",
        # Verb phrases (critical for avoiding mixed EN/BG output)
        "reduce symptoms": "намаляват симптомите",
        "reduces symptoms": "намалява симптомите",
        "reduce pain": "намаляват болката",
        "reduces pain": "намалява болката",
        "reduce fever": "намаляват температурата",
        "reduces fever": "намалява температурата",
        "reduce congestion": "намаляват запушването",
        "reduce swelling": "намаляват отока",
        "reduce": "намаляват",
        "reduces": "намалява",
        "help reduce": "помагат за намаляване на",
        "helps reduce": "помага за намаляване на",
        "help relieve": "помагат за облекчаване на",
        "helps relieve": "помага за облекчаване на",
        "help with": "помагат при",
        "helps with": "помага при",
        "help": "помагат",
        "helps": "помага",
        "relieve symptoms": "облекчават симптомите",
        "relieves symptoms": "облекчава симптомите",
        "relieve pain": "облекчават болката",
        "relieves pain": "облекчава болката",
        "relieve congestion": "облекчават запушването",
        "relieves congestion": "облекчава запушването",
        "relieve": "облекчават",
        "relieves": "облекчава",
        "loosen mucus": "разхлабват слузта",
        "loosens mucus": "разхлабва слузта",
        "making it easier": "като улесняват",
        "makes it easier": "като улеснява",
        "making it easier to cough up": "улеснявайки откашлянето",
        "take as needed": "приемайте при нужда",
        "as needed": "при нужда",
        "last longer": "продължават по-дълго",
        "lasts longer": "продължава по-дълго",
        "longer than": "по-дълго от",
        "works within": "действа в рамките на",
        "work within": "действат в рамките на",
        "works by": "действа чрез",
        "work by": "действат чрез",
        "subside within": "отшумяват в рамките на",
        "subsides within": "отшумява в рамките на",
        "subside": "отшумяват",
        "subsides": "отшумява",
        "last": "продължават",
        "lasts": "продължава",
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
        """Replace common English medical terms with Bulgarian translations.

        Sorts by length (longest first) to ensure proper phrase matching.
        """
        import re

        result = text
        # Sort by length (longest first) to match longer phrases before shorter ones
        sorted_items = sorted(self._MEDICAL_TERM_TRANSLATIONS.items(), key=lambda x: len(x[0]), reverse=True)
        for eng, bg in sorted_items:
            # Case-insensitive replacement
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
        if is_empty_or_whitespace(text):
            return text

        # First, try to translate using dictionary for short/common phrases
        # This catches common medical terms that the model often fails to translate
        dict_result = self._apply_medical_dictionary(text)
        if dict_result != text and self._calculate_bulgarian_ratio(dict_result) > 0.5:
            # Dictionary made significant changes, use it
            return dict_result

        # For long text, translate sentence-by-sentence first (MarianMT does better on short segments)
        SENTENCE_BY_SENTENCE_THRESHOLD = 200
        if len(text.strip()) > SENTENCE_BY_SENTENCE_THRESHOLD and "." in text:
            sentences = [s.strip() for s in text.split(".") if s.strip()]
            if len(sentences) > 1:
                translated_sentences = [self.translate_to_bulgarian(s) for s in sentences]
                return ". ".join(translated_sentences)

        # Check cache
        cached = self._cache_en_to_bg.get(text)
        if cached is not None:
            # Always apply dictionary to cached results too
            return self._apply_medical_dictionary(cached)

        # Load model if needed
        self._load_en_to_bg()

        # Tokenize and translate
        inputs = self._en_to_bg_tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        translated = self._en_to_bg_model.generate(**inputs)
        result = self._en_to_bg_tokenizer.decode(translated[0], skip_special_tokens=True)

        # Always apply dictionary to model output (catches terms model missed)
        result = self._apply_medical_dictionary(result)

        # Check Bulgarian ratio and try additional fallbacks if still low
        bg_ratio = self._calculate_bulgarian_ratio(result)
        if bg_ratio < 0.6 and "." in text:
            # Try sentence-by-sentence translation
            sentences = [s.strip() for s in text.split(".") if s.strip()]
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
                sentence_result = ". ".join(translated_sentences)
                if self._calculate_bulgarian_ratio(sentence_result) > bg_ratio:
                    result = sentence_result

        # Cache result (without dictionary applied - we apply it on retrieval)
        self._cache_en_to_bg.set(text, result)

        # Final cleanup: remove/replace common English words that slip through
        result = self._cleanup_english_remnants(result)

        return result

    # Common English words that slip through translation and their Bulgarian replacements
    # Expanded for Issue 6: mixed English/Bulgarian - target 95%+ Bulgarian
    _ENGLISH_REMNANTS = {
        # Common verbs
        "help": "помага",
        "helps": "помагат",
        "use": "използвайте",
        "take": "вземете",
        "reduce": "намаляват",
        "relieve": "облекчават",
        "relieves": "облекчава",
        "may": "може",
        "can": "може",
        "should": "трябва",
        "loosen": "разхлабят",
        "making": "прави",
        "easier": "по-лесно",
        "last": "продължават",
        "like": "като",
        # Common nouns
        "symptoms": "симптоми",
        "pain": "болка",
        "fever": "температура",
        "cold": "настинка",
        "flu": "грип",
        "cough": "кашлица",
        "doctor": "лекар",
        "medication": "лекарство",
        "medicine": "лекарство",
        "treatment": "лечение",
        "congestion": "запушване",
        "mucus": "слуз",
        "saline": "солен",
        "spray": "спрей",
        "days": "дни",
        "antihistamines": "антихистамини",
        "antipyretics": "антипиретици",
        "decongestants": "деконгестанти",
        # Common adjectives
        "severe": "тежък",
        "mild": "лек",
        "chronic": "хроничен",
        "usual": "обикновено",
        "typically": "обикновено",
        # Common prepositions/connectors
        "with": "с",
        "for": "за",
        "and": "и",
        "or": "или",
        "the": "",  # Remove articles
        "a": "",
        "an": "",
    }

    def _cleanup_english_remnants(self, text: str) -> str:
        """
        Final cleanup pass to replace common English words that slip through translation.

        This catches words the MarianMT model failed to translate, especially
        common verbs, nouns, and connectors.
        """
        import re

        result = text
        for en_word, bg_word in self._ENGLISH_REMNANTS.items():
            # Only replace if word is isolated (not part of a Bulgarian word)
            # Use word boundaries to avoid partial matches
            pattern = rf"\b{re.escape(en_word)}\b"
            result = re.sub(pattern, bg_word, result, flags=re.IGNORECASE)

        # Clean up any double spaces or orphaned punctuation from removed words
        result = re.sub(r"\s+", " ", result)
        result = re.sub(r"\s+([.,!?])", r"\1", result)

        return result.strip()

    def translate_batch_to_bulgarian(self, texts: list[str]) -> list[str]:
        """
        Translate multiple English texts to Bulgarian (more efficient).

        Applies medical dictionary and validates Bulgarian content.

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

        # First pass: try dictionary translation for short/known phrases
        output = list(texts)
        needs_model_translation = []

        for idx, text in non_empty:
            dict_result = self._apply_medical_dictionary(text)
            bg_ratio = self._calculate_bulgarian_ratio(dict_result)

            if bg_ratio > 0.5:
                # Dictionary made good translation
                output[idx] = dict_result
            else:
                # Need model translation
                needs_model_translation.append((idx, text))

        if not needs_model_translation:
            return output

        # Second pass: model translation for remaining texts
        indices, valid_texts = zip(*needs_model_translation, strict=False)
        inputs = self._en_to_bg_tokenizer(
            list(valid_texts), return_tensors="pt", padding=True, truncation=True, max_length=512
        )
        translated = self._en_to_bg_model.generate(**inputs)
        results = [self._en_to_bg_tokenizer.decode(t, skip_special_tokens=True) for t in translated]

        # Apply dictionary, cleanup, and validate each result
        for idx, original, result in zip(indices, valid_texts, results, strict=False):
            # Apply dictionary to model output (catches terms model missed)
            result = self._apply_medical_dictionary(result)
            # Final cleanup: replace English remnants (Issue 6: mixed language)
            result = self._cleanup_english_remnants(result)
            bg_ratio = self._calculate_bulgarian_ratio(result)

            if bg_ratio < 0.4:
                # Model failed - use dictionary result or original with dictionary applied
                dict_fallback = self._apply_medical_dictionary(original)
                dict_fallback = self._cleanup_english_remnants(dict_fallback)
                if self._calculate_bulgarian_ratio(dict_fallback) > bg_ratio:
                    result = dict_fallback

            output[idx] = result

        return output

    def translate_symptom(self, symptom: str) -> str:
        """
        Translate a single symptom term from English to Bulgarian.

        Uses dictionary lookup first, then falls back to model.
        More reliable for short medical terms.

        Args:
            symptom: English symptom term (e.g., "fever", "headache")

        Returns:
            Bulgarian translation
        """
        if is_empty_or_whitespace(symptom):
            return symptom

        symptom_clean = symptom.strip().lower()

        # Direct dictionary lookup (exact match)
        if symptom_clean in self._MEDICAL_TERM_TRANSLATIONS:
            return self._MEDICAL_TERM_TRANSLATIONS[symptom_clean]

        # Try case-insensitive lookup
        for eng, bg in self._MEDICAL_TERM_TRANSLATIONS.items():
            if eng.lower() == symptom_clean:
                return bg

        # Apply dictionary transformation
        dict_result = self._apply_medical_dictionary(symptom)
        if dict_result != symptom and self._calculate_bulgarian_ratio(dict_result) > 0.3:
            return dict_result

        # Fallback to model translation for unknown terms
        translated = self.translate_to_bulgarian(symptom)
        bg_ratio = self._calculate_bulgarian_ratio(translated)

        if bg_ratio < 0.3:
            # Model failed, return original (will be filtered as English)
            return symptom

        return translated

    def clear_cache(self) -> None:
        """Clear the translation cache."""
        self._cache_en_to_bg.clear()
        logger.info("Translation cache cleared")

    def get_cache_stats(self) -> dict:
        """Get cache statistics for monitoring."""
        return {"en_to_bg": self._cache_en_to_bg.stats}


# Global translator instance (lazy loaded, singleton for production)
_translator: Translator | None = None


def get_translator(use_singleton: bool = True) -> Translator:
    """
    Get or create a translator instance with optional singleton bypass.

    Args:
        use_singleton: If True (default), returns cached singleton instance.
                       If False, creates a new instance (useful for testing).

    Returns:
        Translator instance

    Examples:
        # Production: Use singleton
        translator = get_translator()

        # Testing: Create fresh instance
        translator = get_translator(use_singleton=False)
    """
    global _translator

    # If use_singleton=False, create new instance
    if not use_singleton:
        return Translator()

    # Otherwise use singleton pattern
    if _translator is None:
        _translator = Translator()
    return _translator


def reset_translator() -> None:
    """Reset the global translator singleton (useful for testing)."""
    global _translator
    _translator = None
