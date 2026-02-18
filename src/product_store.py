"""
Product vector store using ChromaDB.

Provides semantic search over the product catalogue using
multilingual embeddings. Includes async wrappers for non-blocking operations.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path

import chromadb
from chromadb.config import Settings

from src.data_loader import load_products
from src.logging_config import get_logger

logger = get_logger("viapharma.product_store")


# Default embedding model for multilingual support
DEFAULT_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# ChromaDB collection name
COLLECTION_NAME = "viapharma_products"

# Database path
DB_PATH = "data/chromadb"

# Minimum similarity threshold - products below this are considered irrelevant
MIN_SIMILARITY_THRESHOLD = 0.25

# Keyword boost for exact matches in hybrid search
KEYWORD_BOOST_PER_MATCH = 0.08

# Timeout configuration (prevents slow vector searches)
VECTOR_SEARCH_TIMEOUT_SECONDS = 3.0  # Max time for vector search

# Thread pool for timeout-protected vector search
_search_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vector-search-timeout")

# Treatment type to category mapping for category-aware search
TREATMENT_CATEGORY_MAP = {
    # Pain relief
    "analgesics": ["болкоуспокояващи", "аналгетици", "болка"],
    "pain relief": ["болкоуспокояващи", "аналгетици", "болка"],
    "pain": ["болкоуспокояващи", "аналгетици"],
    # Fever: include "болка" to pull in pure paracetamol/ibuprofen products
    # whose titles say "при болка и температура" (not just cold/flu combos)
    "antipyretics": ["температура", "болка и температура", "парацетамол таблетки"],
    "fever": ["температура", "болка и температура", "парацетамол таблетки"],
    # Allergies
    "antihistamines": ["алергия", "антихистамини"],
    "allergy": ["алергия", "антихистамини"],
    # Digestive
    "antacids": ["стомах", "киселини", "храносмилане"],
    "digestive": ["стомах", "храносмилане", "чревни"],
    "laxatives": ["запек", "разхлабително"],
    "antidiarrheal": ["диария", "разстройство"],
    # Respiratory
    "cough": ["кашлица", "гърло", "простуда"],
    "decongestants": ["хрема", "нос", "синуси"],
    "throat": ["гърло", "болки в гърлото"],
    # Skin
    "topical": ["кожа", "крем", "мехлем"],
    "antiseptic": ["дезинфекция", "рани", "антисептик"],
    # Vitamins/Supplements
    "vitamins": ["витамини", "добавки", "минерали"],
    "supplements": ["добавки", "хранителни добавки"],
}


# Homeopathy detection patterns
_HOMEOPATHY_MARKERS = [
    "хомеопатич",
    "homeopathic",
    "homeopathy",
    "хомеопатия",
    # Potency notations (CH, DH, D, C followed by numbers)
    " ch ",
    " сн ",
    " dh ",
    " дн ",
    "5 ch",
    "9 ch",
    "15 ch",
    "30 ch",
    "200 ch",
    "5 сн",
    "9 сн",
    "15 сн",
    "30 сн",
    "3 dh",
    "6 dh",
    "12 dh",
    "30 dh",
    "3 дн",
    "6 дн",
    "12 дн",
    "boiron",
    "буарон",
]


def _is_homeopathic_product(combined_text: str) -> bool:
    """Detect if a product is homeopathic based on its text content."""
    text = combined_text.lower()
    return any(marker in text for marker in _HOMEOPATHY_MARKERS)


# Mapping from treatment type → ingredient keywords for composition boosting
# These are the actual ingredient names that should appear in product.composition
TREATMENT_INGREDIENT_KEYWORDS = {
    "antipyretics": [
        "парацетамол",
        "paracetamol",
        "acetaminophen",
        "ибупрофен",
        "ibuprofen",
        "аспирин",
        "aspirin",
        "ацетилсалицилова",
        "метамизол",
        "аналгин",
        "metamizole",
    ],
    "analgesics": [
        "парацетамол",
        "paracetamol",
        "acetaminophen",
        "ибупрофен",
        "ibuprofen",
        "диклофенак",
        "diclofenac",
        "напроксен",
        "naproxen",
        "метамизол",
        "аналгин",
        "metamizole",
        "аспирин",
        "aspirin",
    ],
    "antihistamines": [
        "лоратадин",
        "loratadine",
        "цетиризин",
        "cetirizine",
        "фексофенадин",
        "fexofenadine",
    ],
    "antacids": [
        "омепразол",
        "omeprazole",
        "пантопразол",
        "pantoprazole",
        "ранитидин",
        "ranitidine",
    ],
    "antidiarrheal": [
        "лоперамид",
        "loperamide",
        "смектит",
        "smectite",
        "смекта",
    ],
    "cough": [
        "декстрометорфан",
        "dextromethorphan",
        "гвайфенезин",
        "guaifenesin",
    ],
    "decongestants": [
        "псевдоефедрин",
        "pseudoephedrine",
        "фенилефрин",
        "phenylephrine",
        "ксилометазолин",
        "xylometazoline",
        "оксиметазолин",
        "oxymetazoline",
    ],
    "fever": [  # Alias for antipyretics
        "парацетамол",
        "paracetamol",
        "acetaminophen",
        "ибупрофен",
        "ibuprofen",
        "аспирин",
        "aspirin",
        "метамизол",
        "аналгин",
    ],
    "pain relief": [  # Alias for analgesics
        "парацетамол",
        "paracetamol",
        "ибупрофен",
        "ibuprofen",
        "диклофенак",
        "diclofenac",
        "напроксен",
        "naproxen",
    ],
    "pain": [
        "парацетамол",
        "paracetamol",
        "ибупрофен",
        "ibuprofen",
        "диклофенак",
        "diclofenac",
    ],
}


class ProductStore:
    """
    Vector store for product search using ChromaDB.

    Uses sentence-transformers for multilingual embeddings,
    enabling search in both Bulgarian and English.
    """

    def __init__(
        self,
        db_path: str = DB_PATH,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ):
        """
        Initialize the product store.

        Args:
            db_path: Path to ChromaDB database directory
            embedding_model: Sentence transformer model for embeddings
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)

        self.embedding_model_name = embedding_model
        self._embedding_fn = None

        # Initialize ChromaDB with persistent storage
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False),
        )

        self._collection = None

    @property
    def embedding_fn(self):
        """Lazy load embedding function."""
        if self._embedding_fn is None:
            from chromadb.utils import embedding_functions

            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model_name
            )
        return self._embedding_fn

    @property
    def collection(self):
        """Get or create the product collection."""
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=self.embedding_fn,
                metadata={"description": "ViaPharma OTC product catalogue"},
            )
        return self._collection

    def load_products(self, data_dir: str = "output", force_reload: bool = False) -> int:
        """
        Load products from CSV files into ChromaDB.

        Args:
            data_dir: Directory containing product CSV files
            force_reload: If True, delete existing collection and reload

        Returns:
            Number of products loaded
        """
        # Check if already loaded
        if not force_reload and self.collection.count() > 0:
            logger.info(
                f"Collection already contains {self.collection.count()} products. Use force_reload=True to reload."
            )
            return self.collection.count()

        # Delete existing collection if force reload
        if force_reload:
            try:
                self.client.delete_collection(COLLECTION_NAME)
                self._collection = None
                logger.info("Deleted existing collection.")
            except Exception as e:
                logger.debug(f"Collection deletion failed (collection may not exist): {e}")

        # Load and parse products
        products = load_products(data_dir)

        if not products:
            logger.warning("No products to load.")
            return 0

        # Prepare data for ChromaDB (deduplicate by SKU)
        logger.info(f"Preparing {len(products)} products for ChromaDB...")

        ids = []
        documents = []
        metadatas = []
        seen_ids = set()

        for i, product in enumerate(products):
            # Use SKU as ID, fallback to index
            product_id = product.sku if product.sku else f"product_{i}"
            product_id = str(product_id).replace(".0", "")  # Clean float conversion

            # Skip duplicates
            if product_id in seen_ids:
                continue
            seen_ids.add(product_id)

            ids.append(product_id)

            # Searchable text for embeddings
            documents.append(product.to_searchable_text())

            # Metadata for filtering and display
            metadatas.append(product.to_dict())

            if (i + 1) % 1000 == 0:
                logger.debug(f"Prepared {len(ids)}/{len(products)} products (deduped)")

        # Add to ChromaDB in batches
        logger.info("Adding products to ChromaDB...")
        batch_size = 500

        for i in range(0, len(ids), batch_size):
            batch_end = min(i + batch_size, len(ids))
            self.collection.add(
                ids=ids[i:batch_end],
                documents=documents[i:batch_end],
                metadatas=metadatas[i:batch_end],
            )
            logger.debug(f"Added batch {i // batch_size + 1}/{(len(ids) + batch_size - 1) // batch_size}")

        logger.info(f"Loaded {self.collection.count()} products into ChromaDB.")
        return self.collection.count()

    def search(
        self,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
        min_score: float = MIN_SIMILARITY_THRESHOLD,
    ) -> list[dict]:
        """
        Search for products matching the query.

        Args:
            query: Search query (Bulgarian or English)
            n_results: Number of results to return
            where: Optional filter conditions (ChromaDB where clause)
            min_score: Minimum similarity score threshold (0-1)

        Returns:
            List of product dictionaries with similarity scores above threshold
        """
        # Request extra results to account for threshold filtering
        fetch_count = min(n_results * 2, 50)

        results = self.collection.query(
            query_texts=[query],
            n_results=fetch_count,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        products = []
        if results["ids"] and results["ids"][0]:
            for i, product_id in enumerate(results["ids"][0]):
                score = 1 - results["distances"][0][i]  # Convert distance to similarity

                # Filter by minimum similarity threshold
                if score < min_score:
                    logger.debug(f"Filtered out product {product_id} with score {score:.3f} < {min_score}")
                    continue

                product = results["metadatas"][0][i].copy()
                product["id"] = product_id
                product["score"] = score
                products.append(product)

                # Stop once we have enough results
                if len(products) >= n_results:
                    break

        logger.debug(f"Search returned {len(products)} products above threshold {min_score}")
        return products

    def search_by_symptoms(self, symptoms: str, n_results: int = 10) -> list[dict]:
        """
        Search for products that might help with given symptoms.

        Args:
            symptoms: Description of symptoms (Bulgarian or English)
            n_results: Number of results to return

        Returns:
            List of matching products
        """
        # Enhance query with medical context
        enhanced_query = f"лекарство за {symptoms} лечение симптоми"
        return self.search(enhanced_query, n_results=n_results)

    def _keyword_search_fallback(
        self,
        query: str,
        n_results: int = 10,
        preferred_ingredients: list[str] | None = None,
    ) -> list[dict]:
        """
        Simple keyword-based fallback when vector search times out.

        No embeddings needed - just matches query terms in product titles.
        Fast but less accurate than semantic search.

        Args:
            query: Search query
            n_results: Number of results to return
            preferred_ingredients: Optional ingredient keywords to prioritize

        Returns:
            List of products matching query keywords
        """
        logger.warning(
            f"Vector search fallback triggered for query: '{query[:50]}...'",
            extra={"query_length": len(query), "timeout": VECTOR_SEARCH_TIMEOUT_SECONDS}
        )

        # Get all products from collection (this is cached by ChromaDB)
        all_results = self.collection.get(include=["metadatas"])

        if not all_results["ids"]:
            return []

        # Extract query terms
        query_lower = query.lower()
        query_terms = [term for term in query_lower.split() if len(term) > 2]

        # Score products by keyword matches
        scored_products = []
        for i, product_id in enumerate(all_results["ids"]):
            metadata = all_results["metadatas"][i]
            title_lower = metadata.get("title", "").lower()
            brand_lower = metadata.get("brand", "").lower()
            composition_lower = metadata.get("composition", "").lower()
            description_lower = metadata.get("description", "").lower()

            # Count keyword matches
            title_matches = sum(1 for term in query_terms if term in title_lower)
            brand_matches = sum(1 for term in query_terms if term in brand_lower)
            desc_matches = sum(1 for term in query_terms if term in description_lower)

            # Skip if no matches
            if title_matches == 0 and brand_matches == 0 and desc_matches == 0:
                continue

            # Calculate base score (keyword matching only)
            score = (title_matches * 0.3) + (brand_matches * 0.2) + (desc_matches * 0.1)

            # Ingredient boost (if specified)
            if preferred_ingredients:
                combined_text = f"{composition_lower} {title_lower}"
                ingredient_hits = sum(1 for ing in preferred_ingredients if ing.lower() in combined_text)
                if ingredient_hits > 0:
                    score += ingredient_hits * 0.2

            # Homeopathy penalty
            if preferred_ingredients:
                combined_text = f"{composition_lower} {title_lower} {description_lower}"
                if _is_homeopathic_product(combined_text):
                    score -= 0.3

            # Normalize score to 0-1 range
            score = max(0.0, min(1.0, score))

            product = metadata.copy()
            product["id"] = product_id
            product["score"] = score
            product["fallback_search"] = True  # Flag for debugging
            scored_products.append(product)

        # Sort by score and return top N
        scored_products.sort(key=lambda x: x["score"], reverse=True)
        logger.info(
            f"Keyword fallback returned {min(len(scored_products), n_results)} products",
            extra={"total_matches": len(scored_products), "requested": n_results}
        )
        return scored_products[:n_results]

    def hybrid_search(
        self,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
        keyword_boost: float = KEYWORD_BOOST_PER_MATCH,
        preferred_ingredients: list[str] | None = None,
    ) -> list[dict]:
        """
        Hybrid search combining semantic similarity with keyword boosting.

        Improves handling of exact product/brand name queries like "Нурофен" or "Панадол".
        Also supports ingredient-based boosting for symptom-driven selection.

        Includes timeout protection (3s) - falls back to keyword search if vector search is slow.

        Args:
            query: Search query (Bulgarian or English)
            n_results: Number of results to return
            where: Optional filter conditions
            keyword_boost: Score boost per keyword match in title (0-0.2 recommended)
            preferred_ingredients: Optional list of ingredient keywords to boost in
                composition (e.g., ["парацетамол", "paracetamol", "ибупрофен"])

        Returns:
            List of products with combined semantic + keyword scores
        """
        try:
            # Run vector search with timeout protection using concurrent.futures
            future = _search_executor.submit(
                self._run_hybrid_search,
                query,
                n_results,
                where,
                keyword_boost,
                preferred_ingredients
            )
            return future.result(timeout=VECTOR_SEARCH_TIMEOUT_SECONDS)

        except FuturesTimeoutError:
            logger.warning(
                f"Vector search timeout, using keyword fallback",
                extra={"query_preview": query[:50], "timeout": VECTOR_SEARCH_TIMEOUT_SECONDS}
            )
            return self._keyword_search_fallback(
                query,
                n_results=n_results,
                preferred_ingredients=preferred_ingredients
            )
        except Exception as e:
            logger.error(f"Error during hybrid search: {e}", exc_info=True)
            # Fallback to keyword search on any error
            return self._keyword_search_fallback(
                query,
                n_results=n_results,
                preferred_ingredients=preferred_ingredients
            )

    def _run_hybrid_search(
        self,
        query: str,
        n_results: int,
        where: dict | None,
        keyword_boost: float,
        preferred_ingredients: list[str] | None
    ) -> list[dict]:
        """
        Run the actual hybrid search (called in thread pool for timeout protection).

        Args:
            query: Search query
            n_results: Number of results
            where: Optional filter conditions
            keyword_boost: Keyword boost value
            preferred_ingredients: Optional ingredient keywords

        Returns:
            List of products with scores
        """
        # Get more results for re-ranking
        semantic_results = self.search(
            query,
            n_results=n_results * 2,
            where=where,
            min_score=MIN_SIMILARITY_THRESHOLD * 0.8,  # Slightly lower threshold for hybrid
        )

        if not semantic_results:
            return []

        # Extract query terms for keyword matching
        query_lower = query.lower()
        query_terms = [term for term in query_lower.split() if len(term) > 2]

        # Apply keyword boosting
        for product in semantic_results:
            title_lower = product.get("title", "").lower()
            brand_lower = product.get("brand", "").lower()
            composition_lower = product.get("composition", "").lower()

            # Count keyword matches in title and brand
            title_matches = sum(1 for term in query_terms if term in title_lower)
            brand_matches = sum(1 for term in query_terms if term in brand_lower)

            # Exact title match gets higher boost
            exact_title_match = query_lower in title_lower

            # Calculate total boost
            boost = (title_matches * keyword_boost) + (brand_matches * keyword_boost * 0.5)
            if exact_title_match:
                boost += keyword_boost * 2

            # ---- Ingredient-based composition boost (symptom-driven ranking) ----
            # If preferred_ingredients are specified, boost products whose composition
            # contains those ingredients. This ensures e.g. paracetamol/ibuprofen
            # products rank above homeopathy for a fever query.
            if preferred_ingredients:
                combined_text = f"{composition_lower} {title_lower}"
                ingredient_hits = sum(1 for ing in preferred_ingredients if ing.lower() in combined_text)
                if ingredient_hits > 0:
                    # Strong boost: 0.15 per matching ingredient
                    boost += ingredient_hits * 0.15

                    # Extra "simplicity bonus" for single-ingredient products
                    # (not combo cold/flu) — these are more appropriate for
                    # single-symptom queries like "fever" or "headache"
                    combo_markers = [
                        "простуда и грип",
                        "грип и настинка",
                        "настинка и грип",
                        "cold and flu",
                        "cold & flu",
                        "простуда и кашлица",
                        "грипни симптоми",
                    ]
                    desc_lower = product.get("description", "").lower()
                    full_text = f"{title_lower} {desc_lower}"
                    is_combo = any(m in full_text for m in combo_markers)
                    if not is_combo:
                        boost += 0.15  # Extra boost for simple products
                        logger.debug(f"Simplicity bonus for '{product.get('title', '')[:30]}': +0.15")

            # ---- Homeopathy penalty ----
            # Homeopathic products get a score penalty when the search is for
            # a specific clinical treatment type (indicated by preferred_ingredients).
            if preferred_ingredients:
                combined_text = f"{composition_lower} {title_lower} {product.get('description', '').lower()}"
                if _is_homeopathic_product(combined_text):
                    boost -= 0.20  # Significant penalty
                    logger.debug(f"Homeopathy penalty for '{product.get('title', '')[:30]}': -0.20")

            # Apply boost (cap at 1.0, floor at 0.0)
            original_score = product["score"]
            product["score"] = max(0.0, min(1.0, original_score + boost))
            product["keyword_boost"] = boost  # Store for debugging

            if boost > 0:
                logger.debug(
                    f"Keyword boost for '{product.get('title', '')[:30]}': "
                    f"{original_score:.3f} → {product['score']:.3f} (+{boost:.3f})"
                )

        # Re-sort by boosted score and return top N
        semantic_results.sort(key=lambda x: x["score"], reverse=True)
        return semantic_results[:n_results]

    def search_by_category(
        self,
        query: str,
        treatment_type: str,
        n_results: int = 10,
    ) -> list[dict]:
        """
        Category-aware search using treatment type mapping.

        Maps treatment types (from MedGemma) to product categories for better filtering.
        Also passes preferred ingredients for composition-based boosting, ensuring
        symptom-driven selection (e.g., paracetamol for fever, not homeopathy).

        Args:
            query: Search query
            treatment_type: Treatment type from medical reasoning (e.g., "analgesics")
            n_results: Number of results to return

        Returns:
            List of products matching query and category
        """
        treatment_lower = treatment_type.lower().strip()

        # Find matching category keywords
        category_keywords = []
        for key, keywords in TREATMENT_CATEGORY_MAP.items():
            if key in treatment_lower or treatment_lower in key:
                category_keywords.extend(keywords)
                break

        # Find preferred ingredient keywords for this treatment type
        preferred_ingredients = None
        for key, ingredients in TREATMENT_INGREDIENT_KEYWORDS.items():
            if key in treatment_lower or treatment_lower in key:
                preferred_ingredients = ingredients
                break

        if category_keywords:
            # Enhance query with category context
            category_context = " ".join(category_keywords[:2])
            enhanced_query = f"{query} {category_context}"
            logger.debug(f"Category-enhanced query: '{enhanced_query}'")
            return self.hybrid_search(
                enhanced_query,
                n_results=n_results,
                preferred_ingredients=preferred_ingredients,
            )

        # Fallback to regular hybrid search (still with ingredient boost if available)
        return self.hybrid_search(
            query,
            n_results=n_results,
            preferred_ingredients=preferred_ingredients,
        )

    def get_product_by_sku(self, sku: str) -> dict | None:
        """Get a specific product by SKU."""
        results = self.collection.get(
            ids=[sku],
            include=["metadatas"],
        )
        if results["ids"]:
            return results["metadatas"][0]
        return None

    def get_stats(self) -> dict:
        """Get collection statistics."""
        return {
            "total_products": self.collection.count(),
            "db_path": str(self.db_path),
            "embedding_model": self.embedding_model_name,
        }

    # =========================================================================
    # ASYNC METHODS (non-blocking wrappers)
    # =========================================================================

    async def search_async(
        self,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
        min_score: float = MIN_SIMILARITY_THRESHOLD,
    ) -> list[dict]:
        """
        Async version of search - runs in thread pool to avoid blocking event loop.

        Args:
            query: Search query (Bulgarian or English)
            n_results: Number of results to return
            where: Optional filter conditions
            min_score: Minimum similarity threshold

        Returns:
            List of product dictionaries
        """
        return await asyncio.to_thread(self.search, query, n_results, where, min_score)

    async def hybrid_search_async(
        self,
        query: str,
        n_results: int = 10,
        where: dict | None = None,
        keyword_boost: float = KEYWORD_BOOST_PER_MATCH,
    ) -> list[dict]:
        """
        Async version of hybrid_search - runs in thread pool.

        Args:
            query: Search query
            n_results: Number of results
            where: Optional filter conditions
            keyword_boost: Score boost per keyword match

        Returns:
            List of products with combined scores
        """
        return await asyncio.to_thread(self.hybrid_search, query, n_results, where, keyword_boost)

    async def search_by_category_async(
        self,
        query: str,
        treatment_type: str,
        n_results: int = 10,
    ) -> list[dict]:
        """
        Async version of search_by_category - runs in thread pool.

        Args:
            query: Search query
            treatment_type: Treatment type for category mapping
            n_results: Number of results

        Returns:
            List of matching products
        """
        return await asyncio.to_thread(self.search_by_category, query, treatment_type, n_results)


# Global store instance
_store: ProductStore | None = None


def get_product_store() -> ProductStore:
    """Get or create the global product store instance."""
    global _store
    if _store is None:
        _store = ProductStore()
    return _store


if __name__ == "__main__":
    import sys

    store = ProductStore()

    # Check command line args
    if len(sys.argv) > 1 and sys.argv[1] == "--reload":
        store.load_products(force_reload=True)
    else:
        store.load_products()

    # Print stats
    print("\nStore statistics:")
    stats = store.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Test search
    print("\n" + "=" * 60)
    print("Test search: 'главоболие' (headache)")
    print("=" * 60)

    results = store.search("главоболие", n_results=5)
    for i, product in enumerate(results, 1):
        print(f"\n{i}. {product['title']}")
        print(f"   Brand: {product['brand']}")
        print(f"   Price: {product['price_bgn']} лв / {product['price_eur']} €")
        print(f"   Score: {product['score']:.3f}")
        if product.get("description"):
            print(f"   {product['description'][:100]}...")
