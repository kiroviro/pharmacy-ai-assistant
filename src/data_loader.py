"""
Data loader for ViaPharma product catalogue.

Parses Shopify CSV exports and extracts structured product information
for loading into ChromaDB.
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from src.logging_config import get_logger

logger = get_logger("viapharma.data_loader")

# BGN to EUR conversion rate (approximate, update as needed)
BGN_TO_EUR_RATE = 0.51  # 1 BGN ≈ 0.51 EUR (fixed rate in Bulgaria)


@dataclass
class ParsedProduct:
    """Structured product data extracted from Shopify CSV."""

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
    brand: str = ""  # Марка (from Vendor column)
    manufacturer: str = ""  # Производител (from description)

    # Categories
    category: str = ""
    tags: list = field(default_factory=list)
    target_audience: str = ""  # За кого (Възрастни/Деца)
    form: str = ""  # Форма (Сироп, Капсули, etc.)

    # Parsed description sections
    description: str = ""  # Описание
    composition: str = ""  # Състав
    usage: str = ""  # Начин на употреба
    contraindications: str = ""  # Противопоказания
    additional_info: str = ""  # Допълнителна информация

    # Media
    image_url: str = ""

    # Status
    status: str = "Active"
    is_otc: bool = True  # Assume all products are OTC for now

    def to_searchable_text(self) -> str:
        """
        Create a single searchable text combining all relevant fields.
        This will be used for vector embeddings.
        """
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
            "description": self.description[:1000],  # Truncate for metadata
            "composition": self.composition[:500],
            "usage": self.usage[:500],
            "contraindications": self.contraindications[:500],
            "image_url": self.image_url,
            "status": self.status,
            "is_otc": self.is_otc,
        }


class HTMLTextExtractor(HTMLParser):
    """Simple HTML parser to extract plain text."""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag

    def handle_endtag(self, tag):
        if tag in ("p", "h3", "div", "br"):
            self.text_parts.append("\n")
        self.current_tag = None

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.text_parts.append(text)

    def get_text(self) -> str:
        return " ".join(self.text_parts)


def strip_html(html_text: str) -> str:
    """Remove HTML tags and return plain text."""
    if not html_text or pd.isna(html_text):
        return ""

    parser = HTMLTextExtractor()
    try:
        parser.feed(str(html_text))
        text = parser.get_text()
        # Clean up extra whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    except Exception:
        # Fallback: just remove tags with regex
        return re.sub(r"<[^>]+>", " ", str(html_text)).strip()


def extract_section(html_text: str, section_name: str) -> str:
    """
    Extract a specific section from HTML description.

    Sections are marked with <h3>Section Name</h3> followed by content.
    """
    if not html_text or pd.isna(html_text):
        return ""

    # Pattern to match section header and content until next section or end
    pattern = rf"<h3>\s*{re.escape(section_name)}\s*</h3>(.*?)(?=<h3>|$)"
    match = re.search(pattern, str(html_text), re.IGNORECASE | re.DOTALL)

    if match:
        return strip_html(match.group(1))
    return ""


def extract_manufacturer(additional_info: str) -> str:
    """Extract manufacturer from additional info section."""
    if not additional_info:
        return ""

    match = re.search(r"Производител\s*:\s*([^Б\n]+)", additional_info)
    if match:
        # Clean up asterisks and extra whitespace
        return match.group(1).strip().rstrip("*").strip()

    # Fallback: try to get text before "Баркод"
    match = re.search(r"Производител\s*:\s*(.+?)(?=Баркод|$)", additional_info)
    if match:
        return match.group(1).strip().rstrip("*").strip()

    return ""


def extract_barcode_from_desc(additional_info: str) -> str:
    """Extract barcode from additional info section if not in main field."""
    if not additional_info:
        return ""

    match = re.search(r"Баркод\s*:\s*(\d+)", additional_info)
    if match:
        return match.group(1)
    return ""


def parse_product_row(row: pd.Series) -> ParsedProduct:
    """Parse a single product row from the Shopify CSV."""

    # Get raw description HTML
    description_html = str(row.get("Description", "")) if pd.notna(row.get("Description")) else ""

    # Extract sections from description
    description = extract_section(description_html, "Описание")
    composition = extract_section(description_html, "Състав")
    usage = extract_section(description_html, "Начин на употреба")
    contraindications = extract_section(description_html, "Противопоказания")
    additional_info = extract_section(description_html, "Допълнителна информация")

    # Extract manufacturer from additional info
    manufacturer = extract_manufacturer(additional_info)

    # Get barcode - prefer from column, fallback to description
    barcode = str(row.get("Barcode", "")) if pd.notna(row.get("Barcode")) else ""
    if not barcode:
        barcode = extract_barcode_from_desc(additional_info)

    # Parse price
    price_bgn = 0.0
    if pd.notna(row.get("Price")):
        try:
            price_bgn = float(row["Price"])
        except (ValueError, TypeError):
            pass

    # Parse compare-at price
    compare_at = None
    if pd.notna(row.get("Compare-at price")):
        try:
            compare_at = float(row["Compare-at price"])
        except (ValueError, TypeError):
            pass

    # Parse tags
    tags = []
    if pd.notna(row.get("Tags")):
        tags = [t.strip() for t in str(row["Tags"]).split(",") if t.strip()]

    # Clean SKU (remove .0 from float conversion)
    sku = str(row.get("SKU", "")) if pd.notna(row.get("SKU")) else ""
    sku = sku.replace(".0", "") if sku else ""

    return ParsedProduct(
        sku=sku,
        barcode=barcode.replace(".0", "") if barcode else "",
        title=str(row.get("Title", "")) if pd.notna(row.get("Title")) else "",
        url_handle=str(row.get("URL handle", "")) if pd.notna(row.get("URL handle")) else "",
        price_bgn=price_bgn,
        price_eur=round(price_bgn * BGN_TO_EUR_RATE, 2),
        compare_at_price=compare_at,
        brand=str(row.get("Vendor", "")) if pd.notna(row.get("Vendor")) else "",
        manufacturer=manufacturer,
        category=str(row.get("Product category", "")) if pd.notna(row.get("Product category")) else "",
        tags=tags,
        target_audience=str(row.get("За кого (product.metafields.custom.target_audience)", ""))
        if pd.notna(row.get("За кого (product.metafields.custom.target_audience)"))
        else "",
        form=str(row.get("Форма (product.metafields.custom.application_form)", ""))
        if pd.notna(row.get("Форма (product.metafields.custom.application_form)"))
        else "",
        description=description,
        composition=composition,
        usage=usage,
        contraindications=contraindications,
        additional_info=additional_info,
        image_url=str(row.get("Product image URL", "")) if pd.notna(row.get("Product image URL")) else "",
        status=str(row.get("Status", "Active")) if pd.notna(row.get("Status")) else "Active",
    )


def load_products(data_dir: str = "output") -> list[ParsedProduct]:
    """
    Load and parse all product CSVs from the data directory.

    Args:
        data_dir: Directory containing product CSV files

    Returns:
        List of ParsedProduct objects
    """
    data_path = Path(data_dir)
    csv_files = sorted(data_path.glob("products_*.csv"))

    if not csv_files:
        raise FileNotFoundError(f"No product CSV files found in {data_dir}")

    all_products = []

    for csv_file in csv_files:
        logger.info(f"Loading {csv_file.name}...")
        df = pd.read_csv(csv_file, encoding="utf-8")

        # Filter to active products only
        if "Status" in df.columns:
            df = df[df["Status"] == "Active"]

        for _, row in df.iterrows():
            try:
                product = parse_product_row(row)
                if product.title:  # Skip empty rows
                    all_products.append(product)
            except Exception as e:
                logger.warning(f"Error parsing row: {e}")
                continue

        logger.info(f"Loaded {len(df)} products from {csv_file.name}")

    logger.info(f"Total products loaded: {len(all_products)}")
    return all_products


def save_processed_products(products: list[ParsedProduct], output_path: str = "data/products_processed.csv"):
    """Save processed products to a clean CSV for inspection."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    records = [p.to_dict() for p in products]
    df = pd.DataFrame(records)
    df.to_csv(output_file, index=False, encoding="utf-8")
    logger.info(f"Saved processed products to {output_path}")


if __name__ == "__main__":
    # Test the loader
    products = load_products("output")

    # Show sample
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

        # Save processed data
        save_processed_products(products)
