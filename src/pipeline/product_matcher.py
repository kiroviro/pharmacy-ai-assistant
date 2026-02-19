"""
Product matching and ranking for the ViaPharma pipeline.

Handles product candidate retrieval, pharmacological ranking, and deduplication.
Separates product matching logic from orchestration.

Extracted from orchestrator.py as part of Issue #1.
"""

import re

from src.logging_config import get_logger
from src.medical_model import MedicalReasoning
from src.common.models import Product
from src.pipeline.product_ingredients import (
    INGREDIENT_BG_NAMES,
    extract_all_product_ingredients,
    extract_product_ingredient,
    get_recommended_ingredients,
)
from src.pipeline.symptom_mappings import extract_treatment_from_query

logger = get_logger("viapharma.product_matcher")


class ProductMatcher:
    """
    Handles product candidate retrieval, ranking, and filtering.

    Separates product matching logic from Pipeline orchestration.
    Uses two-stage matching:
    1. Fast vector search for candidates (retrieve_candidates)
    2. Optional LLM-based refinement (refine_selection)
    """

    def __init__(self, product_store, medical_model=None):
        """
        Initialize ProductMatcher.

        Args:
            product_store: ChromaDB product store for vector search
            medical_model: Optional medical model for LLM-based refinement
        """
        self.product_store = product_store
        self.medical_model = medical_model

    def retrieve_candidates(
        self,
        medical_reasoning: MedicalReasoning,
        original_query: str = "",
        top_k: int = 10
    ) -> list[Product]:
        """
        Stage 1: Fast vector similarity search to get top-K product candidates.

        Uses ChromaDB with multilingual embeddings based on medical reasoning.
        Includes hybrid search (semantic + keyword) with category awareness.

        Args:
            medical_reasoning: Medical analysis from LLM
            original_query: Original user query for context
            top_k: Number of candidates to retrieve

        Returns:
            List of Product candidates
        """
        if self.product_store.collection.count() == 0:
            logger.warning("Product store is empty. Run product_store.py --reload to load products.")
            return []

        search_query = self._build_search_query(medical_reasoning, original_query)

        # Validate/correct treatment_type using original query keywords
        treatment_type = medical_reasoning.treatment_type
        if original_query:
            query_treatment = extract_treatment_from_query(original_query)
            if query_treatment:
                # Override if MedGemma's treatment doesn't match query symptoms
                if treatment_type:
                    # Check if there's a category mismatch
                    gi_types = {"antidiarrheal", "digestive", "antacids", "laxatives"}
                    cold_types = {"cough", "decongestants", "antipyretics"}

                    # If query has GI symptoms but MedGemma returned cold/flu, override
                    if query_treatment in gi_types and treatment_type.lower() in cold_types:
                        logger.info(
                            f"Overriding treatment_type from '{treatment_type}' to '{query_treatment}' based on query keywords"
                        )
                        treatment_type = query_treatment
                else:
                    treatment_type = query_treatment
                    logger.debug(f"Using query-extracted treatment_type: {treatment_type}")

        # Use category-aware hybrid search for better results
        if treatment_type:
            results = self.product_store.search_by_category(
                query=search_query,
                treatment_type=treatment_type,
                n_results=top_k,
            )
        else:
            # Fallback to hybrid search without category
            results = self.product_store.hybrid_search(search_query, n_results=top_k)

        return self._convert_to_products(results)

    def refine_selection(
        self,
        candidates: list[Product],
        medical_reasoning: MedicalReasoning,
        max_products: int = 3
    ) -> list[Product]:
        """
        Stage 2: LLM-based refinement to pick best matches.

        Optional step - requires medical_model to be provided.
        Falls back to returning top candidates if model not available.

        Args:
            candidates: Product candidates from retrieve_candidates
            medical_reasoning: Medical analysis for relevance scoring
            max_products: Maximum products to return

        Returns:
            Refined list of most relevant products
        """
        if not candidates:
            return []

        # If no medical model, just return top candidates
        if not self.medical_model:
            logger.debug("No medical model available, skipping LLM refinement")
            return candidates[:max_products]

        # Use LLM to refine selection
        try:
            refined = self.medical_model.refine_product_selection(
                user_query=medical_reasoning.likely_cause or "",
                medical_reasoning=medical_reasoning,
                candidate_products=candidates,
                max_products=max_products
            )
            return refined if refined else candidates[:max_products]
        except Exception as e:
            logger.warning(f"LLM refinement failed: {e}, falling back to top candidates")
            return candidates[:max_products]

    def pharmacological_rerank(
        self,
        products: list[Product],
        treatment_type: str
    ) -> list[Product]:
        """
        Rerank products by pharmacological relevance.

        Prioritizes products with ingredients recommended for the treatment type.

        Args:
            products: Products to rerank
            treatment_type: Treatment category (e.g., "analgesics", "cough")

        Returns:
            Reranked products (most relevant first)
        """
        if not products or not treatment_type:
            return products

        recommended_ingredients = get_recommended_ingredients(treatment_type)
        if not recommended_ingredients:
            return products

        # Score each product based on ingredient match
        scored_products = []
        for product in products:
            ingredient = extract_product_ingredient(product)
            score = 2.0 if ingredient in recommended_ingredients else 1.0
            scored_products.append((score, product))

        # Sort by score (descending), then preserve original order for ties
        scored_products.sort(key=lambda x: (-x[0], products.index(x[1])))

        return [product for _, product in scored_products]

    def deduplicate_by_ingredient(
        self,
        products: list[Product],
        max_products: int,
        max_per_ingredient: int = 1
    ) -> list[Product]:
        """
        Remove duplicate products with same active ingredient.

        Keeps the first product per ingredient (assumed to be best/most relevant).

        Args:
            products: Products to deduplicate
            max_products: Maximum total products to return
            max_per_ingredient: Maximum products per ingredient (usually 1)

        Returns:
            Deduplicated products
        """
        if not products:
            return []

        seen_ingredients = {}
        result = []

        for product in products:
            # Extract primary ingredient (or use first word of title as fallback)
            ingredient = extract_product_ingredient(product, fallback_to_title=True)

            # Check if we've seen this ingredient before
            count = seen_ingredients.get(ingredient, 0)
            if count < max_per_ingredient:
                result.append(product)
                seen_ingredients[ingredient] = count + 1

            # Stop once we have enough products
            if len(result) >= max_products:
                break

        return result

    def filter_by_name_match(
        self,
        products: list[Product],
        search_term: str
    ) -> list[Product]:
        """
        Filter products to only those matching search term in title.

        Used for catalog queries where user searches for specific product names.

        Args:
            products: Products to filter
            search_term: Search term to match

        Returns:
            Products matching search term
        """
        if not search_term or len(search_term) < 2:
            return products

        # Generic terms that shouldn't filter aggressively
        generic_terms = {
            "мг", "mg", "мл", "ml", "капсули", "таблетки", "сироп",
            "капки", "крем", "гел", "разтвор", "суспензия",
            "за", "при", "х", "g", "гр"
        }

        # Extract meaningful keywords from search term
        search_lower = search_term.lower()
        keywords = [w for w in search_lower.split() if w not in generic_terms and len(w) > 2]

        if not keywords:
            return products  # No meaningful keywords, return all

        # Filter products by keyword match
        filtered = []
        for product in products:
            title_lower = (product.title or "").lower()
            brand_lower = (product.brand or "").lower()

            # Match if any keyword is in title or brand
            if any(kw in title_lower or kw in brand_lower for kw in keywords):
                filtered.append(product)

        # If filtering removed everything, be lenient and return top results
        if not filtered and products:
            logger.warning(f"No products matched search term '{search_term}', returning top results")
            return products[:3]

        return filtered

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _build_search_query(
        self,
        medical_reasoning: MedicalReasoning,
        original_query: str = ""
    ) -> str:
        """
        Build search query from medical reasoning components.

        Combines treatment type, symptoms, and context for optimal retrieval.

        Args:
            medical_reasoning: Medical analysis
            original_query: Original user query for context

        Returns:
            Search query string
        """
        parts = []

        # Add treatment type (e.g., "analgesics")
        if medical_reasoning.treatment_type:
            parts.append(medical_reasoning.treatment_type)

        # Filter out non-useful symptoms for product search
        non_useful_symptoms = {
            "drug interaction query",
            "drug interaction",
            "safety concern",
            "medication question",
            "dosage question",
            "combination query",
        }
        if medical_reasoning.symptoms:
            useful_symptoms = [s for s in medical_reasoning.symptoms if s.lower() not in non_useful_symptoms]
            parts.extend(useful_symptoms)

        # For drug combo queries, extract actual drug names from original query
        if original_query and self._is_drug_combination_query(original_query):
            drug_names = self._extract_drug_names(original_query)
            if drug_names:
                parts.extend(drug_names)

        # Add likely cause only if it's useful
        if medical_reasoning.likely_cause:
            cause_lower = medical_reasoning.likely_cause.lower()
            if cause_lower not in {"safety concern", "unknown", "not specified"}:
                parts.append(medical_reasoning.likely_cause)

        # For child/baby queries, add age context to retrieval
        if original_query:
            ql = original_query.lower()
            if any(kw in ql for kw in ["бебе", "бебет"]):
                parts.append("бебе бейби за деца")
            elif any(kw in ql for kw in ["дете", "детето", "деца"]):
                parts.append("деца за деца")

        return " ".join(parts) if parts else "medicine"

    def _is_drug_combination_query(self, query: str) -> bool:
        """Check if query is asking about drug combinations/interactions."""
        query_lower = query.lower()
        combo_patterns = [
            "може ли",
            "мога ли",
            "заедно",
            "комбиниране",
            "комбинация",
            "взаимодействие",
            "interaction",
            "combine",
            "together",
            "with",
            "и",
            "+",
        ]
        # Count how many combo indicators present
        indicators = sum(1 for pattern in combo_patterns if pattern in query_lower)
        # Also check for multiple drug mentions
        has_multiple_drugs = self._count_drug_mentions(query) >= 2
        return indicators >= 1 and has_multiple_drugs

    def _count_drug_mentions(self, query: str) -> int:
        """Count number of drug name mentions in query."""
        query_lower = query.lower()
        common_drugs = [
            "парацетамол", "paracetamol", "ибупрофен", "ibuprofen",
            "аспирин", "aspirin", "нурофен", "nurofen", "панадол", "panadol",
            "диклофенак", "diclofenac", "метамизол", "analgin"
        ]
        return sum(1 for drug in common_drugs if drug in query_lower)

    def _extract_drug_names(self, query: str) -> list[str]:
        """Extract drug names from query for drug combination searches."""
        query_lower = query.lower()
        drugs = []

        # Common drug patterns
        drug_patterns = {
            "paracetamol": ["парацетамол", "paracetamol", "панадол", "panadol"],
            "ibuprofen": ["ибупрофен", "ibuprofen", "нурофен", "nurofen"],
            "aspirin": ["аспирин", "aspirin"],
            "diclofenac": ["диклофенак", "diclofenac"],
            "metamizole": ["метамизол", "аналгин", "analgin"],
        }

        for canonical, patterns in drug_patterns.items():
            if any(p in query_lower for p in patterns):
                drugs.append(canonical)

        return drugs

    # Note: _extract_treatment_from_query moved to src/pipeline/symptom_mappings.py
    # for centralized symptom mapping management

    def _convert_to_products(self, results: list) -> list[Product]:
        """
        Convert ChromaDB results to Product objects.

        Args:
            results: Raw results from ChromaDB (list of dicts)

        Returns:
            List of Product objects
        """
        products = []
        for item in results:
            try:
                product = Product.from_chromadb(item) if isinstance(item, dict) else item
                products.append(product)
            except Exception as e:
                logger.warning(f"Failed to convert result to Product: {e}")
                continue
        return products
