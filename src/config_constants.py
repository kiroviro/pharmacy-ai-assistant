"""
Configuration constants for the ViaPharma pipeline.

Contains magic numbers extracted from across the codebase for easier tuning.
These values control search behavior, response formatting, and quality thresholds.
"""

# =============================================================================
# VECTOR SEARCH CONFIGURATION
# =============================================================================
# Controls how many products are retrieved and filtered at each stage

# Number of candidates to retrieve from vector search (Stage 1)
VECTOR_SEARCH_TOP_K = 10

# Number of products to fetch for catalog queries
CATALOG_SEARCH_SIZE = 12

# Maximum products in final response after LLM refinement (Stage 2)
MAX_REFINED_PRODUCTS = 3

# Extra products fetched for deduplication buffer
DEDUP_EXTRA_PRODUCTS = 2

# Maximum products per active ingredient to avoid redundancy
MAX_PRODUCTS_PER_INGREDIENT = 1


# =============================================================================
# RESPONSE FORMATTING
# =============================================================================
# Controls what gets displayed in the final response

# Maximum products shown in catalog listing
MAX_CATALOG_PRODUCTS = 3

# Product detail display limit for catalog queries
CATALOG_DISPLAY_LIMIT = 5

# Fallback products when filtering removes all results
TOP_K_FALLBACK_PRODUCTS = 3

# Maximum symptoms to display in response
MAX_SYMPTOMS_DISPLAY = 5

# Maximum character length for individual symptom display
MAX_SYMPTOM_LENGTH = 40

# Maximum self-care tips to include
MAX_SELF_CARE_TIPS = 3

# Self-care tip length bounds
MIN_TIP_LENGTH = 5
MAX_TIP_LENGTH = 100

# Maximum duration guidance text length
MAX_DURATION_LENGTH = 120

# Maximum warnings to display
MAX_WARNINGS = 3

# Maximum contraindicated products to mention
MAX_CONTRAINDICATED_DISPLAY = 3


# =============================================================================
# QUALITY THRESHOLDS
# =============================================================================
# Controls filtering based on quality scores

# Minimum Bulgarian character ratio for translation quality
MIN_BULGARIAN_RATIO_THRESHOLD = 0.3

# Bulgarian ratio threshold for translation retry
MIN_BULGARIAN_RATIO_FOR_TRANSLATION = 0.6

# Minimum search term length for filtering
MIN_SEARCH_TERM_LENGTH = 2


# =============================================================================
# MODEL INFERENCE
# =============================================================================
# Controls MedGemma behavior (some already in medical_model.py)

# Max tokens for medical reasoning response
MAX_TOKENS_MEDICAL_REASONING = 200

# Sampling temperature for medical reasoning (0.0-1.0)
MEDICAL_REASONING_TEMPERATURE = 0.3

# Max tokens for product selection response
MAX_TOKENS_PRODUCT_SELECTION = 50

# Temperature for product selection (deterministic)
PRODUCT_SELECTION_TEMPERATURE = 0.0


# =============================================================================
# TEXT TRUNCATION
# =============================================================================
# Controls how text fields are truncated in prompts/responses

# Product description max length in prompts
DESCRIPTION_MAX_LENGTH = 200

# Composition text max length
COMPOSITION_MAX_LENGTH = 150

# Contraindications text max length
CONTRAINDICATIONS_MAX_LENGTH = 200


# =============================================================================
# SEARCH BOOSTING
# =============================================================================
# Controls relevance scoring multipliers

# Multiplier for brand match boost
BRAND_MATCH_BOOST_MULTIPLIER = 0.5

# Multiplier for exact title match boost
EXACT_MATCH_BOOST_MULTIPLIER = 2

# Fetch multiplier for threshold filtering buffer
SEARCH_FETCH_MULTIPLIER = 2

# Maximum products to fetch before filtering
MAX_SEARCH_FETCH_COUNT = 50

# Ratio of main threshold for hybrid search
HYBRID_SEARCH_THRESHOLD_RATIO = 0.8


# =============================================================================
# CACHING
# =============================================================================
# Cache sizes and related settings

# ChromaDB batch size for bulk operations
CHROMADB_BATCH_SIZE = 500

# Translation cache size
TRANSLATION_CACHE_SIZE = 1000

# Tokenizer max sequence length
TOKENIZER_MAX_LENGTH = 512
