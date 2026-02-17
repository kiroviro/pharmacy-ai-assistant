"""
Lightweight safety classifier using sentence embeddings.

Compares user input against known dangerous phrase embeddings.
No fine-tuning required - uses semantic similarity for detection.
"""

from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer

from src.logging_config import get_logger

logger = get_logger("viapharma.safety_embeddings")


@dataclass
class EmbeddingSafetyResult:
    """Result from embedding-based safety classification."""

    severity: str  # emergency, urgent, warning, safe
    confidence: float
    matched_phrase: str | None
    similarity_score: float


class EmbeddingSafetyClassifier:
    """
    Semantic safety classifier using sentence embeddings.

    Detects dangerous phrases even with:
    - Paraphrasing ("want to end it all" -> suicidal)
    - Typos ("не мога да дъшам")
    - Transliteration ("ne moga da disham")
    - Different wording for same concept
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        """
        Initialize with a multilingual embedding model.

        Args:
            model_name: SentenceTransformer model (118MB, supports 50+ languages)
        """
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self._init_reference_embeddings()
        logger.info("Embedding safety classifier initialized")

    def _init_reference_embeddings(self):
        """Pre-compute embeddings for reference dangerous phrases."""

        self.emergency_phrases = [
            # Breathing/cardiac
            "не мога да дишам",
            "задушавам се",
            "затруднено дишане",
            "болка в гърдите",
            "стягане в гърдите",
            "can't breathe",
            "difficulty breathing",
            "choking",
            "chest pain",
            "chest tightness",
            "heart attack",
            # Poisoning/overdose
            "детето ми изпи лекарство",
            "бебето глътна хапче",
            "изпих твърде много хапчета",
            "предозирах",
            "отрових се",
            "child swallowed pills",
            "baby ate medication",
            "overdose",
            "poisoning",
            # Mental health crisis
            "искам да се убия",
            "искам да умра",
            "не искам да живея",
            "суицидни мисли",
            "самонараняване",
            "режа се",
            "want to kill myself",
            "want to die",
            "suicidal thoughts",
            "self-harm",
            "cutting myself",
            "want to end it all",
            # Severe allergic
            "не мога да преглъщам",
            "подуване на гърлото",
            "анафилаксия",
            "can't swallow",
            "throat swelling",
            "anaphylaxis",
            # Stroke/neurological
            "не мога да говоря",
            "парализа",
            "изтръпване на лицето",
            "can't speak",
            "paralysis",
            "face drooping",
            # Other emergencies
            "силно кървене",
            "гърчове",
            "загубих съзнание",
            "severe bleeding",
            "seizure",
            "unconscious",
        ]

        self.urgent_phrases = [
            # Blood symptoms
            "кръв в урината",
            "кръв в изпражненията",
            "повръщам кръв",
            "blood in urine",
            "blood in stool",
            "vomiting blood",
            # Fever
            "висока температура повече от 3 дни",
            "температура над 39",
            "high fever for 3 days",
            "fever over 39",
            # Severe pain
            "силна коремна болка",
            "болка в бъбреците",
            "най-силното главоболие в живота ми",
            "severe abdominal pain",
            "kidney pain",
            "worst headache ever",
            # Other urgent
            "не мога да уринирам",
            "жълти очи",
            "жълтеница",
            "объркан съм",
            "схванат врат с температура",
            "can't urinate",
            "yellow eyes",
            "jaundice",
            "confused",
            "stiff neck with fever",
        ]

        self.warning_phrases = [
            # Persistent symptoms
            "кашлица повече от 2 седмици",
            "постоянна умора",
            "отслабвам без причина",
            "нощно изпотяване",
            "cough for weeks",
            "constant fatigue",
            "unexplained weight loss",
            "night sweats",
            # Lumps/skin changes
            "бучка",
            "бенка се промени",
            "рана която не зараства",
            "lump",
            "mole changed",
            "wound not healing",
            # Other warnings
            "чести главоболия",
            "замъглено зрение",
            "frequent headaches",
            "blurred vision",
        ]

        # Pre-compute normalized embeddings
        logger.info("Computing reference embeddings...")
        self.emergency_embeddings = self.model.encode(
            self.emergency_phrases, convert_to_numpy=True, normalize_embeddings=True
        )
        self.urgent_embeddings = self.model.encode(
            self.urgent_phrases, convert_to_numpy=True, normalize_embeddings=True
        )
        self.warning_embeddings = self.model.encode(
            self.warning_phrases, convert_to_numpy=True, normalize_embeddings=True
        )
        logger.info(
            f"Embeddings ready: {len(self.emergency_phrases)} emergency, "
            f"{len(self.urgent_phrases)} urgent, {len(self.warning_phrases)} warning"
        )

    def classify(
        self,
        text: str,
        emergency_threshold: float = 0.82,
        urgent_threshold: float = 0.85,
        warning_threshold: float = 0.85,
    ) -> EmbeddingSafetyResult:
        """
        Classify user input by similarity to dangerous phrases.

        Args:
            text: User input text
            emergency_threshold: Min similarity for emergency (default 0.65)
            urgent_threshold: Min similarity for urgent (default 0.65)
            warning_threshold: Min similarity for warning (default 0.60)

        Returns:
            EmbeddingSafetyResult with severity and matched phrase
        """
        if not text or not text.strip():
            return EmbeddingSafetyResult("safe", 1.0, None, 0.0)

        # Encode user input (normalized for cosine similarity)
        user_embedding = self.model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0]

        # Check emergency first
        emergency_sims = np.dot(self.emergency_embeddings, user_embedding)
        max_em_idx = int(np.argmax(emergency_sims))
        max_em_sim = float(emergency_sims[max_em_idx])

        if max_em_sim >= emergency_threshold:
            logger.warning(f"EMERGENCY via embedding: {max_em_sim:.2f}")
            return EmbeddingSafetyResult("emergency", max_em_sim, self.emergency_phrases[max_em_idx], max_em_sim)

        # Check urgent
        urgent_sims = np.dot(self.urgent_embeddings, user_embedding)
        max_ur_idx = int(np.argmax(urgent_sims))
        max_ur_sim = float(urgent_sims[max_ur_idx])

        if max_ur_sim >= urgent_threshold:
            logger.warning(f"URGENT via embedding: {max_ur_sim:.2f}")
            return EmbeddingSafetyResult("urgent", max_ur_sim, self.urgent_phrases[max_ur_idx], max_ur_sim)

        # Check warning
        warning_sims = np.dot(self.warning_embeddings, user_embedding)
        max_wa_idx = int(np.argmax(warning_sims))
        max_wa_sim = float(warning_sims[max_wa_idx])

        if max_wa_sim >= warning_threshold:
            logger.info(f"WARNING via embedding: {max_wa_sim:.2f}")
            return EmbeddingSafetyResult("warning", max_wa_sim, self.warning_phrases[max_wa_idx], max_wa_sim)

        # Safe
        max_sim = max(max_em_sim, max_ur_sim, max_wa_sim)
        return EmbeddingSafetyResult("safe", 1.0 - max_sim, None, max_sim)


# Singleton (lazy loaded)
_classifier: EmbeddingSafetyClassifier | None = None


def get_embedding_safety_classifier() -> EmbeddingSafetyClassifier:
    """Get or create the global embedding safety classifier."""
    global _classifier
    if _classifier is None:
        _classifier = EmbeddingSafetyClassifier()
    return _classifier
