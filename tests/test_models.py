"""
Unit tests for pipeline data models (Product, etc.).

Note: Importing src.pipeline.models pulls in medical_model (mlx). These tests
run when the full env is available. For quick model-only checks, run with
CI/no-Metal env that uses mocked imports.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline.models import Product


@pytest.fixture(autouse=True)
def mock_settings():
    """Avoid config/settings dependency in unit tests."""
    with patch("src.pipeline.models.get_settings") as m:
        m.return_value.product_base_url = "https://viapharma.bg/products"
        yield m


class TestProductToDisplayString:
    """Tests for Product.to_display_string()."""

    def test_includes_image_when_image_url_present(self):
        """Product with image_url should render Markdown image after title."""
        p = Product(
            id="p1",
            title="Нурофен 200mg",
            url_handle="nurofen-200",
            price_bgn=5.99,
            price_eur=3.05,
            description="Обезболяващо и жаропонижаващо.",
            image_url="https://example.com/nurofen.jpg",
        )
        out = p.to_display_string()
        assert "## [Нурофен 200mg]" in out or "## [Нурофен" in out
        assert "![Нурофен 200mg](https://example.com/nurofen.jpg)" in out
        assert "---\n🛒 **[Виж продукта / Купи]" in out
        assert "**\n---" in out

    def test_no_image_when_image_url_empty(self):
        """Product without image_url should not render image."""
        p = Product(
            id="p1",
            title="Парацетамол 500mg",
            url_handle="paracetamol-500",
            price_bgn=4.99,
            price_eur=2.54,
            description="Обезболяващо.",
            image_url="",
        )
        out = p.to_display_string()
        assert "![" not in out and "<img" not in out
        assert "## [Парацетамол" in out or "## Парацетамол" in out

    def test_no_image_when_image_url_whitespace_only(self):
        """Product with only whitespace image_url should not render image."""
        p = Product(
            id="p1",
            title="Ибупрофен",
            url_handle="ibuprofen",
            price_bgn=6.99,
            price_eur=3.56,
            image_url="   \n  ",
        )
        out = p.to_display_string()
        assert "![" not in out and "<img" not in out
