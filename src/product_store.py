"""
Product vector store using ChromaDB.

Provides semantic search over the product catalogue using
multilingual embeddings. Includes async wrappers for non-blocking operations.
"""

import asyncio
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

from src.data_loader import ParsedProduct, load_products
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

# Treatment type to category mapping for category-aware search
TREATMENT_CATEGORY_MAP = {
    # Pain relief
    "analgesics": ["болкоуспокояващи", "аналгетици", "болка"],
    "pain relief": ["болкоуспокояващи", "аналгетици", "болка"],
    "pain": ["болкоуспокояващи", "аналгетици"],
    # Fever
    "antipyretics": ["температура", "антипиретици", "простуда"],
    "fever": ["температура", "антипиретици", "простуда"],
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
            logger.info(f"Collection already contains {self.collection.count()} products. Use force_reload=True to reload.")
            return self.collection.count()

        # Delete existing collection if force reload
        if force_reload:
            try:
                self.client.delete_collection(COLLECTION_NAME)
                self._collection = None
                logger.info("Deleted existing collection.")
            except Exception:
                pass

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
        where: Optional[dict] = None,
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

    def hybrid_search(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[dict] = None,
        keyword_boost: float = KEYWORD_BOOST_PER_MATCH,
    ) -> list[dict]:
        """
        Hybrid search combining semantic similarity with keyword boosting.

        Improves handling of exact product/brand name queries like "Нурофен" or "Панадол".

        Args:
            query: Search query (Bulgarian or English)
            n_results: Number of results to return
            where: Optional filter conditions
            keyword_boost: Score boost per keyword match in title (0-0.2 recommended)

        Returns:
            List of products with combined semantic + keyword scores
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

            # Count keyword matches in title and brand
            title_matches = sum(1 for term in query_terms if term in title_lower)
            brand_matches = sum(1 for term in query_terms if term in brand_lower)

            # Exact title match gets higher boost
            exact_title_match = query_lower in title_lower

            # Calculate total boost
            boost = (title_matches * keyword_boost) + (brand_matches * keyword_boost * 0.5)
            if exact_title_match:
                boost += keyword_boost * 2

            # Apply boost (cap at 1.0)
            original_score = product["score"]
            product["score"] = min(1.0, original_score + boost)
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

        if category_keywords:
            # Enhance query with category context
            category_context = " ".join(category_keywords[:2])
            enhanced_query = f"{query} {category_context}"
            logger.debug(f"Category-enhanced query: '{enhanced_query}'")
            return self.hybrid_search(enhanced_query, n_results=n_results)

        # Fallback to regular hybrid search
        return self.hybrid_search(query, n_results=n_results)

    def get_product_by_sku(self, sku: str) -> Optional[dict]:
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
        where: Optional[dict] = None,
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
        return await asyncio.to_thread(
            self.search, query, n_results, where, min_score
        )

    async def hybrid_search_async(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[dict] = None,
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
        return await asyncio.to_thread(
            self.hybrid_search, query, n_results, where, keyword_boost
        )

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
        return await asyncio.to_thread(
            self.search_by_category, query, treatment_type, n_results
        )


# Global store instance
_store: Optional[ProductStore] = None


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
        if product.get('description'):
            print(f"   {product['description'][:100]}...")
