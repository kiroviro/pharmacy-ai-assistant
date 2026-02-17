"""
Intent Classifier for filtering non-medical queries.

Uses keyword-based classification with medical terms in Bulgarian and English.
Fast and efficient - no ML model needed for this use case.

DEPRECATION NOTICE:
==================
    Status: DEPRECATED - Scheduled for removal
    Replacement: src/unified_processor.py (LLM-based semantic classification)

    Timeline:
    - Phase 1 (Current): Runs in parallel with unified processor as fallback
    - Phase 2 (v2.0): Will emit deprecation warnings when used
    - Phase 3 (v3.0): Will be removed entirely

    Migration Path:
    1. Set VIAPHARMA_UNIFIED_PROCESSOR_ENABLED=true in your environment
    2. Test that unified processor handles your queries correctly
    3. Report any classification issues to improve unified processor
    4. Once stable, remove intent_classifier imports from your code

    Why Deprecated:
    - Keyword matching cannot understand semantic context
    - False positives on words like "delivery", "payment" that contain medical substrings
    - Cannot handle novel phrasing or misspellings
    - Unified processor uses LLM for true intent understanding

    Set VIAPHARMA_UNIFIED_PROCESSOR_ENABLED=true to use the new system.
"""

import re


class IntentClassifier:
    """
    Classifies user queries as medical or non-medical.

    Uses keyword matching with:
    - Bulgarian medical terms
    - English medical terms (in case translation happens first)
    - Common symptom words
    - Body part references
    """

    def __init__(self):
        # Bulgarian medical/symptom keywords
        self.bg_medical_keywords = {
            # Symptoms
            'болка', 'боли', 'болки', 'болест', 'болен', 'болна',
            'температура', 'треска', 'висока температура',
            'главоболие', 'мигрена',
            'кашлица', 'кашлям', 'кихане', 'кихам',
            'хрема', 'запушен нос', 'течащ нос',
            'гадене', 'повръщане', 'повръщам',
            'диария', 'запек', 'разстройство',
            'умора', 'уморен', 'уморена', 'слабост',
            'замаяност', 'световъртеж', 'виене на свят',
            'сърбеж', 'сърби', 'обрив', 'зачервяване',
            'подуване', 'оток', 'подут', 'подута',
            'възпаление', 'инфекция',
            'алергия', 'алергичен', 'алергична',
            'безсъние', 'не мога да спя',
            'стрес', 'тревожност', 'депресия',

            # Body parts
            'глава', 'гърло', 'гърди', 'гръден кош',
            'корем', 'стомах', 'черва',
            'гръб', 'кръст', 'врат',
            'ръка', 'ръце', 'крак', 'крака',
            'око', 'очи', 'ухо', 'уши', 'нос', 'уста',
            'зъб', 'зъби', 'венци',
            'кожа', 'коса', 'нокти',
            'мускул', 'мускули', 'става', 'стави',
            'сърце', 'бял дроб', 'черен дроб', 'бъбрек',

            # Medical actions
            'лекарство', 'лекарства', 'таблетка', 'таблетки',
            'сироп', 'капки', 'мехлем', 'крем',
            'лечение', 'лекувам', 'помощ',
            'симптом', 'симптоми', 'диагноза',
            'рецепта', 'без рецепта', 'аптека',
            'витамин', 'витамини', 'добавка', 'добавки',
            'болкоуспокояващо', 'антибиотик',
            'какво да взема', 'какво помага', 'какво да направя',
            'препоръчай', 'препоръчайте', 'посъветвай',

            # Age-specific (children/babies)
            'бебе', 'бебета', 'бебешки', 'бебешка',
            'дете', 'деца', 'детски', 'детска',
            'новородено', 'кърмаче',
            'дозировка за дете', 'доза за дете',
        }

        # English medical keywords (backup if query comes in English)
        self.en_medical_keywords = {
            # Symptoms
            'pain', 'ache', 'hurt', 'hurts', 'sore',
            'fever', 'temperature', 'cold', 'flu',
            'headache', 'migraine',
            'cough', 'sneeze', 'runny nose', 'congestion',
            'nausea', 'vomiting', 'diarrhea', 'constipation',
            'fatigue', 'tired', 'weakness', 'exhausted',
            'dizzy', 'dizziness', 'vertigo',
            'itch', 'itchy', 'rash', 'swelling', 'swollen',
            'inflammation', 'infection', 'allergy', 'allergic',
            'insomnia', 'anxiety', 'stress', 'depression',

            # Body parts
            'head', 'throat', 'chest', 'stomach', 'abdomen',
            'back', 'neck', 'arm', 'leg', 'hand', 'foot',
            'eye', 'ear', 'nose', 'mouth', 'tooth', 'teeth',
            'skin', 'muscle', 'joint', 'heart', 'lung',

            # Medical actions
            'medicine', 'medication', 'drug', 'tablet', 'pill',
            'syrup', 'cream', 'ointment', 'drops',
            'treatment', 'remedy', 'cure', 'relief',
            'symptom', 'symptoms', 'diagnosis',
            'pharmacy', 'prescription', 'otc', 'over the counter',
            'vitamin', 'supplement', 'painkiller', 'antibiotic',
            'recommend', 'suggest', 'help', 'what should i take',
        }

        # Non-medical keywords (strong indicators of off-topic)
        self.non_medical_keywords = {
            # Bulgarian - general
            'времето', 'прогноза', 'температура навън',
            'новини', 'спорт', 'футбол', 'мач',
            'рецепта за', 'готвене', 'храна', 'ресторант',
            'филм', 'музика', 'песен', 'книга',
            'пътуване', 'самолет', 'хотел', 'резервация',
            'работа', 'офис', 'среща', 'проект',
            'банка', 'пари', 'кредит', 'сметка',
            'шега', 'виц', 'смешно',

            # Bulgarian - e-commerce/delivery/payment
            'доставка', 'доставката', 'доставя', 'доставяне',
            'колко време се доставя', 'кога ще пристигне',
            'поръчка', 'поръчката', 'поръчам', 'поръчвам',
            'статус на поръчка', 'проследя', 'проследяване',
            'плащане', 'платя', 'плащам', 'начин на плащане',
            'карта', 'с карта', 'банкова карта', 'кредитна карта',
            'наложен платеж', 'в брой', 'кеш',
            'връщане', 'върна', 'връщам', 'да върна продукт',
            'фактура', 'получа фактура', 'данъчна фактура',
            'отстъпка', 'промоция', 'намаление', 'по-голяма поръчка',
            'цена на доставка', 'цената на доставката', 'безплатна доставка',
            'работно време', 'адрес на аптека', 'къде се намирате',

            # Bulgarian - prices / promotions
            'промоции', 'колко струва', 'цена', 'цени', 'ценово',
            'програма за лоялни', 'лоялни клиенти', 'промо код', 'промокод',
            'ддс', 'разпродажба', 'абонамент', 'абонаментни',
            'по-скъпо', 'по-евтино', 'струва', 'скъп', 'евтин',

            # Bulgarian - account management
            'акаунт', 'парола', 'имейл адрес', 'регистрация',
            'вход', 'профил', 'история на поръчките', 'любими',
            'изтрия акаунт', 'данни', 'защитени', 'лични данни',
            'забравих парола', 'възстановя парола', 'променя имейл',

            # Bulgarian - navigation / site
            'сайт', 'уебсайт', 'страница', 'приложение', 'мобилно',
            'не зарежда', 'свържа', 'контакт', 'физически аптеки', 'ревю', 'рецензия', 'блог',
            'намеря продукт', 'търсачка', 'категории',

            # Bulgarian - legal / regulatory
            'лиценз', 'контролира', 'gdpr', 'политика',
            'иал', 'разрешение', 'регулация',

            # Bulgarian - returns (additional)
            'повреден', 'повреда', 'дефект', 'рекламация',
            'грешен продукт', 'изтекъл срок', 'възстановяване на парите',

            # Bulgarian - meta / about chatbot
            'чатбот', 'бот', 'робот', 'жив човек',
            'направил', 'създал', 'разработил',
            'политическа', 'ориентация',
            'кафене', 'магазин',

            # English - general
            'weather', 'forecast', 'news', 'sports', 'football',
            'recipe', 'cooking', 'restaurant', 'food',
            'movie', 'music', 'song', 'book',
            'travel', 'flight', 'hotel', 'booking',
            'work', 'office', 'meeting', 'project',
            'bank', 'money', 'loan', 'account',
            'joke', 'funny', 'tell me a',

            # English - e-commerce/delivery/payment
            'delivery', 'shipping', 'deliver', 'ship',
            'order', 'order status', 'track order', 'tracking',
            'payment', 'pay', 'pay with card', 'credit card',
            'cash on delivery', 'cod',
            'return', 'refund', 'return product',
            'invoice', 'receipt',
            'discount', 'promotion', 'sale',
            'free shipping', 'delivery cost', 'shipping cost',

            # English - account / meta
            'password', 'email address', 'registration', 'login',
            'profile', 'order history', 'favorites', 'wishlist',
            'chatbot', 'bot', 'robot', 'human', 'real person',
            'who made', 'who created', 'political',
        }

        # Profanity/inappropriate language (Bulgarian and English)
        self.profanity_keywords = {
            # Bulgarian vulgar words
            'ебаваш', 'ебеш', 'ебати', 'еба', 'ебал', 'ебана',
            'путка', 'пишка', 'кур', 'гъз', 'задник',
            'дебил', 'идиот', 'тъпак', 'глупак', 'малоумен',
            'мамка', 'копеле', 'педал', 'педераст',
            'шибан', 'проклет', 'мръсник',
            'боклук', 'измет', 'лайно', 'лайна',

            # English vulgar words
            'fuck', 'fucking', 'shit', 'bullshit', 'damn',
            'ass', 'asshole', 'bitch', 'bastard',
            'idiot', 'moron', 'stupid', 'dumb',
            'crap', 'suck', 'sucks',
        }

        # Compile patterns for efficiency
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for keyword matching."""
        # Create word boundary patterns for more accurate matching
        bg_pattern = '|'.join(re.escape(kw) for kw in self.bg_medical_keywords)
        en_pattern = '|'.join(re.escape(kw) for kw in self.en_medical_keywords)
        non_med_pattern = '|'.join(re.escape(kw) for kw in self.non_medical_keywords)

        # Profanity needs word boundaries to avoid false positives
        # e.g. "бебе" should not match profanity patterns
        profanity_pattern = '|'.join(
            r'\b' + re.escape(kw) + r'\b' for kw in self.profanity_keywords
        )

        self._bg_medical_pattern = re.compile(f'({bg_pattern})', re.IGNORECASE)
        self._en_medical_pattern = re.compile(f'\\b({en_pattern})\\b', re.IGNORECASE)
        self._non_medical_pattern = re.compile(f'({non_med_pattern})', re.IGNORECASE)
        self._profanity_pattern = re.compile(f'({profanity_pattern})', re.IGNORECASE)

    def is_medical_query(self, text: str) -> tuple[bool, float, str]:
        """
        Classify if the query is medical-related.

        Args:
            text: User query text

        Returns:
            Tuple of (is_medical, confidence, reason)
            - is_medical: True if query appears to be medical
            - confidence: 0.0 to 1.0 confidence score
            - reason: Explanation of classification
        """
        if not text or not text.strip():
            return False, 0.0, "Empty query"

        text_lower = text.lower()

        # Count matches
        bg_matches = len(self._bg_medical_pattern.findall(text_lower))
        en_matches = len(self._en_medical_pattern.findall(text_lower))
        non_med_matches = len(self._non_medical_pattern.findall(text_lower))
        profanity_matches = len(self._profanity_pattern.findall(text_lower))

        medical_matches = bg_matches + en_matches

        # Decision logic

        # Reject profanity/inappropriate language immediately
        if profanity_matches > 0:
            return False, 0.99, "Inappropriate language detected"

        # Reject clearly non-medical queries
        if non_med_matches > 0 and medical_matches == 0:
            return False, 0.9, f"Non-medical keywords detected: {non_med_matches}"

        # Accept strong medical signals
        if medical_matches >= 2:
            return True, 0.95, f"Multiple medical keywords: {medical_matches}"

        if medical_matches == 1:
            return True, 0.7, "Single medical keyword found"

        # Short queries without medical keywords - reject
        if len(text.split()) < 4 and medical_matches == 0:
            return False, 0.6, "Short non-medical query"

        # No clear indicators - assume medical (be permissive for longer queries)
        # Better to process a non-medical query than reject a medical one
        return True, 0.3, "No clear indicators, defaulting to medical"

    def get_rejection_message(self, language: str = "bg", reason: str = "") -> str:
        """
        Get a polite rejection message for non-medical queries.

        Args:
            language: "bg" for Bulgarian, "en" for English
            reason: Classification reason (used to customize message)

        Returns:
            Rejection message
        """
        # Special message for inappropriate language
        if "inappropriate" in reason.lower() or "profanity" in reason.lower():
            if language == "bg":
                return (
                    "Моля, използвайте подходящ език. "
                    "Аз съм аптечен асистент и мога да помогна само с въпроси за здраве и лекарства."
                )
            else:
                return (
                    "Please use appropriate language. "
                    "I'm a pharmacy assistant and can only help with health and medication questions."
                )

        # Standard rejection for non-medical queries
        if language == "bg":
            return (
                "Съжалявам, но мога да помогна само с въпроси, свързани със здравето и лекарства. "
                "Моля, опишете вашите симптоми или попитайте за конкретен здравословен проблем."
            )
        else:
            return (
                "I'm sorry, but I can only help with health and medication-related questions. "
                "Please describe your symptoms or ask about a specific health concern."
            )


# Global instance
_intent_classifier: IntentClassifier | None = None


def get_intent_classifier() -> IntentClassifier:
    """Get or create the global intent classifier instance."""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifier()
    return _intent_classifier
