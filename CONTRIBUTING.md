# Contributing to ViaPharma OTC Chatbot

Thank you for your interest in contributing to the ViaPharma OTC Chatbot project!

## Development Setup

### Prerequisites

- Python 3.11+
- Mac with Apple Silicon (M1/M2/M3) for MedGemma inference
- ~8GB disk space for models

### Quick Setup

```bash
# Clone the repository
git clone <repository-url>
cd medgemma

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development tools

# Download the MedGemma model
huggingface-cli login
huggingface-cli download mlx-community/medgemma-4b-it-bf16 --local-dir models/medgemma-4b-it-bf16

# Run tests to verify setup
pytest tests/ -v
```

## Project Structure

```
medgemma/
├── src/                    # Source code
│   ├── pipeline/           # Main pipeline (modular)
│   │   ├── orchestrator.py # Pipeline class
│   │   ├── models.py       # Product, PipelineResult
│   │   ├── constants.py    # Keywords, patterns
│   │   └── conditions.py   # Condition extraction
│   ├── medical_model.py    # MedGemma wrapper
│   ├── translator.py       # BG↔EN translation
│   ├── safety.py          # Emergency detection
│   ├── product_store.py   # ChromaDB vector store
│   └── intent_classifier.py
├── tests/                  # Test suite
├── data/                   # Product data, embeddings
├── models/                 # Downloaded models
└── docs/                   # Documentation
```

## Code Style

### Python Standards

- **Formatting**: We don't enforce a specific formatter, but keep code clean and readable
- **Type hints**: Use type hints for function signatures
- **Docstrings**: Document public functions with Args/Returns sections

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

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_translator.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Run only fast tests (skip slow LLM tests)
pytest tests/ -v -m "not slow"
```

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
- **Regression tests**: Prevent re-introducing bugs (see `TestRegressionPrevention`)

## Making Changes

### Before Starting

1. Check existing issues for related work
2. For significant changes, open an issue to discuss first
3. Create a branch from `main`

### Development Workflow

1. **Write tests first** for any new functionality
2. Make your changes
3. Run the test suite: `pytest tests/ -v`
4. Update documentation if needed

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

## Safety Considerations

This is a medical-adjacent application. Please:

- **Never remove safety checks** without discussion
- **Test edge cases** for medical content
- **Preserve emergency detection** for critical symptoms
- **Maintain disclaimers** for medical advice

### Critical Safety Files

- `src/safety.py` - Emergency keyword detection
- Pipeline safety layer integration
- Disclaimer generation

## Translation Dictionary

The medical dictionary in `src/translator.py` ensures consistent translations.

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
3. Update `docs/pipeline_diagram.md` if flow changes

## Getting Help

- Check existing documentation in `docs/`
- Review the `ARCHITECTURE.md` for system design
- Open an issue for questions

## Code of Conduct

- Be respectful and constructive
- Focus on the code, not the person
- Help newcomers get started

Thank you for contributing!
