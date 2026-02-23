"""
Data loader for ViaPharma product catalogue.

Reads from data/products_processed.csv — the pre-processed flat CSV produced
by the pharmacy-to-shopify pipeline and kept up-to-date by price_sync.py.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.logging_config import get_logger

logger = get_logger("viapharma.data_loader")


@dataclass
class ParsedProduct:
    """Structured product data extracted from the processed CSV."""

    # Core identifiers
    sku: str
    barcode: str
    title: str
    url_handle: str

    # Pricing
    price_bgn: float
    price_eur: float
    compare_at_price: float | None = None

    # Brand/Vendor
    brand: str = ""
    manufacturer: str = ""

    # Categories
    category: str = ""
    tags: list = field(default_factory=list)
    target_audience: str = ""  # За кого (Възрастни/Деца)
    form: str = ""  # Форма (Сироп, Капсули, etc.)

    # Description sections
    description: str = ""
    composition: str = ""
    usage: str = ""
    contraindications: str = ""
    additional_info: str = ""

    # Media
    image_url: str = ""

    # Status
    status: str = "Active"
    is_otc: bool = True

    def to_searchable_text(self) -> str:
        """Create a single searchable text combining all relevant fields for vector embeddings."""
        parts = [
            self.title,
            f"Марка: {self.brand}" if self.brand else "",
            f"Категория: {self.category}" if self.category else "",
            self.description,
            f"Състав: {self.composition}" if self.composition else "",
            f"Начин на употреба: {self.usage}" if self.usage else "",
            f"Противопоказания: {self.contraindications}" if self.contraindications else "",
        ]
        return "\n".join(p for p in parts if p)

    def to_dict(self) -> dict:
        """Convert to dictionary for ChromaDB metadata."""
        return {
            "sku": self.sku,
            "barcode": self.barcode,
            "title": self.title,
            "url_handle": self.url_handle,
            "price_bgn": self.price_bgn,
            "price_eur": self.price_eur,
            "brand": self.brand,
            "manufacturer": self.manufacturer,
            "category": self.category,
            "tags": ", ".join(self.tags),
            "target_audience": self.target_audience,
            "form": self.form,
            "description": self.description[:1000],
            "composition": self.composition[:500],
            "usage": self.usage[:500],
            "contraindications": self.contraindications[:500],
            "image_url": self.image_url,
            "status": self.status,
            "is_otc": self.is_otc,
        }


def _str(val) -> str:
    """Return string value or empty string for NaN/None."""
    return str(val) if pd.notna(val) else ""


def _float(val) -> float:
    """Return float value or 0.0 for NaN/None/invalid."""
    if pd.notna(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return 0.0


def load_products(data_dir: str = "data") -> list[ParsedProduct]:
    """
    Load products from data/products_processed.csv.

    Args:
        data_dir: Directory containing products_processed.csv (default: "data")

    Returns:
        List of ParsedProduct objects with status == "Active"
    """
    csv_path = Path(data_dir) / "products_processed.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Product CSV not found: {csv_path}")

    logger.info(f"Loading products from {csv_path}...")
    df = pd.read_csv(csv_path, encoding="utf-8")

    # Filter to active products only
    if "status" in df.columns:
        df = df[df["status"] == "Active"]

    products = []
    for _, row in df.iterrows():
        try:
            title = _str(row.get("title"))
            if not title:
                continue  # Skip empty rows

            # SKU and barcode: strip float-conversion artefact (e.g. "3490.0" → "3490")
            sku = _str(row.get("sku")).replace(".0", "")
            barcode = _str(row.get("barcode")).replace(".0", "")

            tags = (
                [t.strip() for t in _str(row.get("tags")).split(",") if t.strip()]
                if pd.notna(row.get("tags"))
                else []
            )

            is_otc = _str(row.get("is_otc")).strip().lower() == "true"

            products.append(
                ParsedProduct(
                    sku=sku,
                    barcode=barcode,
                    title=title,
                    url_handle=_str(row.get("url_handle")),
                    price_bgn=_float(row.get("price_bgn")),
                    price_eur=_float(row.get("price_eur")),
                    brand=_str(row.get("brand")),
                    manufacturer=_str(row.get("manufacturer")),
                    category=_str(row.get("category")),
                    tags=tags,
                    target_audience=_str(row.get("target_audience")),
                    form=_str(row.get("form")),
                    description=_str(row.get("description")),
                    composition=_str(row.get("composition")),
                    usage=_str(row.get("usage")),
                    contraindications=_str(row.get("contraindications")),
                    image_url=_str(row.get("image_url")),
                    status=_str(row.get("status")) or "Active",
                    is_otc=is_otc,
                )
            )
        except Exception as e:
            logger.warning(f"Error parsing row (sku={row.get('sku', '?')}): {e}")
            continue

    logger.info(f"Loaded {len(products)} active products from {csv_path}")
    return products


if __name__ == "__main__":
    products = load_products()

    if products:
        print("\n" + "=" * 60)
        print("Sample product:")
        print("=" * 60)
        p = products[0]
        print(f"Title: {p.title}")
        print(f"Brand: {p.brand}")
        print(f"Price: {p.price_bgn} лв / {p.price_eur} €")
        print(f"Category: {p.category}")
        print(f"Description: {p.description[:200]}...")
        print(f"Composition: {p.composition[:200]}..." if p.composition else "Composition: N/A")
        print(f"Contraindications: {p.contraindications[:200]}..." if p.contraindications else "Contraindications: N/A")
        print(f"Image: {p.image_url}")
