# Contributing to Pharmacy AI Assistant

Thank you for your interest in contributing to the Pharmacy AI Assistant project!

## Development Setup

### Prerequisites

- Python 3.11+
- Mac with Apple Silicon (M1/M2/M3/M4) for MedGemma inference via MLX
- ~8GB disk space for models

### Quick Setup

```bash
# Clone the repository
git clone https://github.com/kiroviro/pharmacy-ai-assistant.git
cd pharmacy-ai-assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Download the MedGemma model
huggingface-cli login
huggingface-cli download mlx-community/medgemma-4b-it-bf16 --local-dir models/medgemma-4b-it-bf16

# Run tests to verify setup
pytest tests/ -v
```

## Project Structure

```
pharmacy-ai-assistant/
├── src/
│   ├── pipeline/                    # Main pipeline (modular)
│   │   ├── orchestrator.py          # Pipeline class (~1,210 LOC)
│   │   ├── product_matcher.py       # Product search & ranking
│   │   ├── safety_validator.py      # Age/severity filtering
│   │   ├── ingredient_analyzer.py   # Ingredient extraction
│   │   ├── response_builder.py      # Response formatting
│   │   ├── response_validator.py    # Garbage text filtering
│   │   ├── query_router.py          # Query routing
│   │   ├── product_ingredients.py   # Ingredient parsing
│   │   ├── conditions.py            # Condition extraction
│   │   └── models.py                # Product, PipelineResult
│   ├── services/                    # Service layer
│   │   ├── medical_reasoning_service.py
│   │   ├── product_recommendation_service.py
│   │   └── safety_check_service.py
│   ├── unified_processor.py         # LLM-driven processor
│   ├── medical_model.py             # MedGemma MLX wrapper
│   ├── translator.py                # EN→BG translation (MarianMT)
│   ├── safety.py                    # Hard-coded emergency detection
│   ├── product_store.py             # ChromaDB vector store
│   ├── config.py                    # Centralized config (pydantic-settings)
│   └── prompts/
│       └── unified_prompt.py        # LLM prompt templates
├── tests/
│   ├── e2e/                         # E2E quality tests (5 files)
│   ├── contracts/                   # Test contracts & builders
│   └── test_*.py                    # Unit & integration tests
├── data/                            # Product data, ChromaDB
├── models/                          # Downloaded models (git-ignored)
└── docs/                            # Architecture, tech debt
```

## Code Style

### Python Standards

- **Formatting & Linting**: [ruff](https://github.com/astral-sh/ruff) (line-length=120)
- **Type hints**: Use type hints for function signatures
- **Docstrings**: Document public functions — only where the logic isn't self-evident

### Naming Conventions

- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private methods: `_leading_underscore`

### Import Order

1. Standard library
2. Third-party packages
3. Local imports (`from src...`)

## Testing

### Running Tests

#### Unit Tests

```bash
# Run all unit tests
pytest tests/ -v

# Run specific test file
pytest tests/test_translator.py -v

# Run with coverage (enforced minimum: 35%)
pytest tests/ --cov=src --cov-report=term-missing

# Run only fast tests (skip slow LLM tests)
pytest tests/ -v -m "not slow"
```

#### End-to-End (E2E) Quality Tests

```bash
# Run all E2E tests
pytest tests/e2e/ -v

# Run by category
pytest tests/e2e/test_symptom_queries.py -v
pytest tests/e2e/test_medication_queries.py -v
pytest tests/e2e/test_safety_queries.py -v
pytest tests/e2e/test_catalog_queries.py -v
pytest tests/e2e/test_edge_cases.py -v
```

**What E2E Tests Check**:
- **Garbage text detection**: Ensures no irrelevant text in responses
- **Template compliance**: Validates response structure (ingredients, safety warnings, etc.)
- **Language quality**: Confirms responses are >95% Bulgarian
- **Product relevance**: Verifies recommended products match symptoms
- **Safety validation**: Tests emergency detection and triage
- **Performance**: Tracks response times (target <10s)

### Writing Tests

- Place tests in `tests/` directory
- Name test files `test_*.py`
- Use pytest fixtures for setup
- Use parametrized tests for multiple inputs:

```python
@pytest.mark.parametrize("input,expected", [
    ("headache", "hlavobolie"),
    ("fever", "temperatura"),
])
def test_translation(input, expected):
    assert translate(input) == expected
```

### Test Categories

- **Unit tests**: Test individual functions/methods
- **Integration tests**: Test component interactions
- **Contract tests**: Test interface contracts (survive refactoring)
- **E2E tests**: Full pipeline quality validation

## Making Changes

### Before Starting

1. Check existing issues for related work
2. For significant changes, open an issue to discuss first
3. Create a branch from `main`

### Development Workflow

1. **Write tests first** for any new functionality
2. Make your changes
3. Run the test suite: `pytest tests/ -v`
4. Run linting: `ruff check src/ tests/`
5. Update documentation if needed

### Commit Messages

Use clear, descriptive commit messages:

```
Add retry logic to model inference

- Implement exponential backoff for transient failures
- Add MAX_INFERENCE_RETRIES configuration
- Update both medical reasoning and product selection
```

### Pull Request Guidelines

1. **Keep PRs focused**: One feature/fix per PR
2. **Include tests**: New code should have test coverage
3. **Update docs**: If behavior changes, update relevant docs
4. **Run all tests**: Ensure `pytest tests/ -v` passes
5. **Lint passes**: Ensure `ruff check` passes

## Safety Considerations

This is a medical-adjacent application. Please:

- **Never remove the hard-coded safety layer** (`src/safety.py`) — this is non-negotiable
- **Test edge cases** for medical content
- **Preserve emergency detection** for critical symptoms
- **Maintain disclaimers** for medical advice
- **MLX is single-threaded** — `max_workers=1` is correct; concurrent inference causes segfault

### Critical Safety Files

- `src/safety.py` — Hard-coded emergency keyword detection
- `src/pipeline/safety_validator.py` — Age/severity filtering
- `src/services/safety_check_service.py` — Safety check service

## Translation Dictionary

The medical dictionary in `src/translator.py` handles EN→BG translation (BG→EN query translation is handled by the unified processor).

### Adding Terms

When adding medical terms to the dictionary:

1. Add both singular and plural forms
2. Include Bulgarian grammatical variations
3. Add a test case in `tests/test_translator.py`:

```python
@pytest.mark.parametrize("english,expected_bulgarian", [
    ("new_term", "new_translation"),
])
def test_new_term_translation(self, translator, english, expected_bulgarian):
    result = translator._apply_medical_dictionary(english)
    assert expected_bulgarian in result
```

## Common Tasks

### Adding a New Product Field

1. Update `src/pipeline/models.py` (Product dataclass)
2. Update `src/product_store.py` (ChromaDB schema)
3. Add tests for the new field

### Adding Emergency Keywords

1. Update `src/safety.py` (EMERGENCY_KEYWORDS)
2. Add test case verifying detection
3. Test false positive scenarios

### Modifying Pipeline Flow

1. Review `src/pipeline/orchestrator.py`
2. Consider impacts on caching
3. Update `docs/ARCHITECTURE.md` if flow changes

## Getting Help

- Check existing documentation in `docs/`
- Review `docs/ARCHITECTURE.md` for system design
- Open an issue for questions

## Code of Conduct

- Be respectful and constructive
- Focus on the code, not the person
- Help newcomers get started

Thank you for contributing!
