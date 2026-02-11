"""
Product vector store using ChromaDB.

Provides semantic search over the product catalogue using
multilingual embeddings.
"""

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
    ) -> list[dict]:
        """
        Search for products matching the query.

        Args:
            query: Search query (Bulgarian or English)
            n_results: Number of results to return
            where: Optional filter conditions (ChromaDB where clause)

        Returns:
            List of product dictionaries with similarity scores
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        products = []
        if results["ids"] and results["ids"][0]:
            for i, product_id in enumerate(results["ids"][0]):
                product = results["metadatas"][0][i].copy()
                product["id"] = product_id
                product["score"] = 1 - results["distances"][0][i]  # Convert distance to similarity
                products.append(product)

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
