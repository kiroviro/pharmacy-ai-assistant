# Data Directory

This directory contains product catalog data and embeddings for the ViaPharma OTC chatbot.

## Product Catalog Format

The chatbot expects a CSV file at `data/products.csv` (or `data/products_processed.csv`) with the following columns:

| Column | Type | Required | Description |
|--------|------|----------|-------------|
| `sku` | string | Yes | Unique product identifier |
| `barcode` | string | No | Product barcode/EAN |
| `title` | string | Yes | Product name (Bulgarian) |
| `url_handle` | string | No | URL slug for product page |
| `price_bgn` | float | Yes | Price in Bulgarian Leva |
| `price_eur` | float | No | Price in Euros |
| `brand` | string | No | Product brand name |
| `manufacturer` | string | No | Manufacturer name |
| `category` | string | No | Product category |
| `tags` | string | No | Comma-separated tags |
| `target_audience` | string | No | Target demographic (e.g., "adults", "children") |
| `form` | string | No | Medication form (e.g., "tablets", "syrup", "cream") |
| `description` | string | Yes | Product description (Bulgarian) |
| `composition` | string | No | Active ingredients |
| `usage` | string | No | Usage instructions |
| `contraindications` | string | No | Contraindications and warnings |
| `image_url` | string | No | Product image URL |
| `status` | string | No | Product status (e.g., "active", "discontinued") |
| `is_otc` | boolean | Yes | `true` for OTC products, `false` for prescription-only |

## Example Row

```csv
sku,barcode,title,url_handle,price_bgn,price_eur,brand,manufacturer,category,tags,target_audience,form,description,composition,usage,contraindications,image_url,status,is_otc
"PARA-500-20","5060123456789","Парацетамол 500мг x20 таблетки","paracetamol-500mg-20","8.99","4.60","GenericPharma","Generic Pharmaceuticals Ltd","Обезболяващи","hlavobolie,temperatura,grip","възрастни","таблетки","Обезболяващо и жароснижаващо средство за лечение на главоболие, мускулни болки и грип","Парацетамол 500мг","Възрастни: 1-2 таблетки до 4 пъти дневно","Не използвайте при чернодробни проблеми или алергия към парацетамол","https://example.com/paracetamol.jpg","active","true"
```

## Data Sources

Product data is typically imported from the **pharmacy-to-shopify** synchronization pipeline, which pulls the latest product catalog from viapharma.us.

## ChromaDB Embeddings

The `chromadb/` directory contains vector embeddings generated from product descriptions. This database is automatically created when you run:

```bash
python -c "from src.product_store import get_product_store; ps = get_product_store(); ps.reload_products()"
```

The embeddings enable semantic search for product recommendations based on symptom descriptions.

## Metrics & Queries

- `metrics/` - Performance metrics from evaluation runs (git-ignored)
- `queries/` - Query logs for testing and analysis (git-ignored)

Both directories are excluded from version control but preserved for local development.
