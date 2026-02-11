"""
Intent Classifier for filtering non-medical queries.

Uses keyword-based classification with medical terms in Bulgarian and English.
Fast and efficient - no ML model needed for this use case.
"""

import re
from typing import Optional


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
            # Bulgarian
            'времето', 'прогноза', 'температура навън',
            'новини', 'спорт', 'футбол', 'мач',
            'рецепта за', 'готвене', 'храна', 'ресторант',
            'филм', 'музика', 'песен', 'книга',
            'пътуване', 'самолет', 'хотел', 'резервация',
            'работа', 'офис', 'среща', 'проект',
            'банка', 'пари', 'кредит', 'сметка',
            'шега', 'виц', 'смешно',

            # English
            'weather', 'forecast', 'news', 'sports', 'football',
            'recipe', 'cooking', 'restaurant', 'food',
            'movie', 'music', 'song', 'book',
            'travel', 'flight', 'hotel', 'booking',
            'work', 'office', 'meeting', 'project',
            'bank', 'money', 'loan', 'account',
            'joke', 'funny', 'tell me a',
        }

        # Compile patterns for efficiency
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for keyword matching."""
        # Create word boundary patterns for more accurate matching
        bg_pattern = '|'.join(re.escape(kw) for kw in self.bg_medical_keywords)
        en_pattern = '|'.join(re.escape(kw) for kw in self.en_medical_keywords)
        non_med_pattern = '|'.join(re.escape(kw) for kw in self.non_medical_keywords)

        self._bg_medical_pattern = re.compile(f'({bg_pattern})', re.IGNORECASE)
        self._en_medical_pattern = re.compile(f'\\b({en_pattern})\\b', re.IGNORECASE)
        self._non_medical_pattern = re.compile(f'({non_med_pattern})', re.IGNORECASE)

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

        medical_matches = bg_matches + en_matches

        # Decision logic
        if non_med_matches > 0 and medical_matches == 0:
            return False, 0.9, f"Non-medical keywords detected: {non_med_matches}"

        if medical_matches >= 2:
            return True, 0.95, f"Multiple medical keywords: {medical_matches}"

        if medical_matches == 1:
            return True, 0.7, f"Single medical keyword found"

        # No clear indicators - assume medical (be permissive)
        # Better to process a non-medical query than reject a medical one
        return True, 0.3, "No clear indicators, defaulting to medical"

    def get_rejection_message(self, language: str = "bg") -> str:
        """
        Get a polite rejection message for non-medical queries.

        Args:
            language: "bg" for Bulgarian, "en" for English

        Returns:
            Rejection message
        """
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
_intent_classifier: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """Get or create the global intent classifier instance."""
    global _intent_classifier
    if _intent_classifier is None:
        _intent_classifier = IntentClassifier()
    return _intent_classifier
