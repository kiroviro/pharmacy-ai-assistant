"""
Data models for the ViaPharma pipeline.

Contains Product and PipelineResult dataclasses.
"""

from dataclasses import dataclass, field
from typing import Optional

from src.config import get_settings
from src.medical_model import MedicalReasoning


@dataclass
class Product:
    """Represents a product from the catalogue."""
    id: str
    title: str  # Product name
    brand: str = ""  # Марка
    manufacturer: str = ""  # Производител
    category: str = ""
    tags: str = ""
    url_handle: str = ""  # URL slug for product link

    # Pricing
    price_bgn: float = 0.0  # Price in лв
    price_eur: float = 0.0  # Price in €

    # Product details
    description: str = ""  # Описание
    composition: str = ""  # Състав
    usage: str = ""  # Начин на употреба
    contraindications: str = ""  # Противопоказания

    # Additional info
    barcode: str = ""
    image_url: str = ""
    target_audience: str = ""  # За кого
    form: str = ""  # Форма
    is_otc: bool = True

    # Search relevance
    score: float = 0.0

    @property
    def product_url(self) -> str:
        """Get the full URL to the product page."""
        if self.url_handle:
            base_url = get_settings().product_base_url
            return f"{base_url}/{self.url_handle}"
        return ""

    @classmethod
    def from_chromadb(cls, data: dict) -> "Product":
        """Create a Product from ChromaDB search result."""
        return cls(
            id=str(data.get("id", data.get("sku", ""))),
            title=data.get("title", ""),
            brand=data.get("brand", ""),
            manufacturer=data.get("manufacturer", ""),
            category=data.get("category", ""),
            tags=data.get("tags", ""),
            url_handle=data.get("url_handle", ""),
            price_bgn=float(data.get("price_bgn", 0)),
            price_eur=float(data.get("price_eur", 0)),
            description=data.get("description", ""),
            composition=data.get("composition", ""),
            usage=data.get("usage", ""),
            contraindications=data.get("contraindications", ""),
            barcode=data.get("barcode", ""),
            image_url=data.get("image_url", ""),
            target_audience=data.get("target_audience", ""),
            form=data.get("form", ""),
            is_otc=data.get("is_otc", True),
            score=float(data.get("score", 0)),
        )

    def to_display_string(self) -> str:
        """Format product for display in chat with clean markdown."""
        lines = []

        # Title - make it a link if URL available
        if self.product_url:
            lines.append(f"**[{self.title}]({self.product_url})**")
        else:
            lines.append(f"**{self.title}**")

        # Price and brand on same line
        price_line = f"💰 {self.price_bgn:.2f} лв ({self.price_eur:.2f} €)"
        if self.brand:
            price_line += f"  •  🏷️ {self.brand}"
        lines.append(price_line)

        # Description - clean formatting, smart truncation
        if self.description:
            desc = self.description[:300].strip()
            if len(self.description) > 300:
                # Cut at last complete sentence or word
                last_period = desc.rfind('.')
                if last_period > 200:
                    desc = desc[:last_period + 1]
                else:
                    desc = desc.rsplit(' ', 1)[0] + "..."
            lines.append(f"\n{desc}")

        # Add to cart link
        if self.product_url:
            lines.append(f"\n🛒 [Виж продукта / Купи]({self.product_url})")

        return "\n".join(lines)


@dataclass
class PipelineResult:
    """Result from the pipeline processing."""
    response: str
    is_medical: bool = True
    is_red_flag: bool = False
    original_text: str = ""
    translated_text: str = ""
    medical_reasoning: Optional[MedicalReasoning] = None
    candidate_products: list = field(default_factory=list)  # Stage 1: top-K from vector DB
    selected_products: list = field(default_factory=list)   # Stage 2: LLM-refined selection
    # Contraindication filtering results
    user_conditions: list = field(default_factory=list)  # Detected user conditions (pregnancy, diabetes, etc.)
    contraindicated_products: list = field(default_factory=list)  # Products filtered due to contraindications
