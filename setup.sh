#!/bin/bash
# ViaPharma OTC Chatbot - One-command setup script
# Usage: ./setup.sh [--skip-model] [--skip-venv]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
SKIP_MODEL=false
SKIP_VENV=false
for arg in "$@"; do
    case $arg in
        --skip-model)
            SKIP_MODEL=true
            shift
            ;;
        --skip-venv)
            SKIP_VENV=true
            shift
            ;;
    esac
done

echo -e "${GREEN}=== ViaPharma OTC Chatbot Setup ===${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "${RED}Error: Python 3.10+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi
echo -e "  Python: ${GREEN}$PYTHON_VERSION${NC}"

# Check if on Apple Silicon
if [[ $(uname -m) == "arm64" ]]; then
    echo -e "  Apple Silicon: ${GREEN}Yes${NC}"
else
    echo -e "  ${YELLOW}Warning: Not on Apple Silicon - MLX may not work optimally${NC}"
fi

# Step 1: Create virtual environment
if [ "$SKIP_VENV" = false ]; then
    if [ ! -d "venv" ]; then
        echo ""
        echo -e "${YELLOW}Step 1: Creating virtual environment...${NC}"
        python3 -m venv venv
        echo -e "  ${GREEN}Created venv/${NC}"
    else
        echo ""
        echo -e "${YELLOW}Step 1: Virtual environment already exists${NC}"
    fi

    # Activate virtual environment
    source venv/bin/activate
    echo -e "  ${GREEN}Activated virtual environment${NC}"
else
    echo ""
    echo -e "${YELLOW}Step 1: Skipping virtual environment (--skip-venv)${NC}"
fi

# Step 2: Install dependencies
echo ""
echo -e "${YELLOW}Step 2: Installing dependencies...${NC}"
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo -e "  ${GREEN}Dependencies installed${NC}"

# Step 3: Download MedGemma model
if [ "$SKIP_MODEL" = false ]; then
    echo ""
    echo -e "${YELLOW}Step 3: Downloading MedGemma model...${NC}"

    MODEL_DIR="models/medgemma-4b-it-bf16"
    if [ -d "$MODEL_DIR" ] && [ -f "$MODEL_DIR/config.json" ]; then
        echo -e "  ${GREEN}Model already exists at $MODEL_DIR${NC}"
    else
        echo -e "  This may take a while (~8GB download)"
        echo -e "  ${YELLOW}Note: Requires Hugging Face login for MedGemma access${NC}"

        # Check if logged in to Hugging Face
        if ! huggingface-cli whoami &>/dev/null; then
            echo ""
            echo -e "  ${YELLOW}Please log in to Hugging Face:${NC}"
            huggingface-cli login
        fi

        # Download model
        huggingface-cli download mlx-community/medgemma-4b-it-bf16 --local-dir "$MODEL_DIR"
        echo -e "  ${GREEN}Model downloaded${NC}"
    fi
else
    echo ""
    echo -e "${YELLOW}Step 3: Skipping model download (--skip-model)${NC}"
fi

# Step 4: Create necessary directories
echo ""
echo -e "${YELLOW}Step 4: Creating directories...${NC}"
mkdir -p data/chroma_db
mkdir -p output
mkdir -p logs
echo -e "  ${GREEN}Directories created${NC}"

# Step 5: Initialize product store (if data exists)
echo ""
echo -e "${YELLOW}Step 5: Checking product data...${NC}"
if [ -f "data/products.csv" ]; then
    echo -e "  Found data/products.csv"
    echo -e "  ${YELLOW}Initializing product store...${NC}"
    python3 -c "from src.product_store import get_product_store; ps = get_product_store(); print(f'  Loaded {ps.product_count()} products')" 2>/dev/null || echo -e "  ${YELLOW}Note: Run product reload separately if needed${NC}"
else
    echo -e "  ${YELLOW}No product data found at data/products.csv${NC}"
    echo -e "  Place your product CSV there and run:"
    echo -e "  python -c \"from src.product_store import get_product_store; ps = get_product_store(); ps.reload_products()\""
fi

# Step 6: Run quick tests
echo ""
echo -e "${YELLOW}Step 6: Running quick tests...${NC}"
if python3 -m pytest tests/test_translator.py tests/test_safety.py -v --tb=short -q 2>/dev/null; then
    echo -e "  ${GREEN}Tests passed${NC}"
else
    echo -e "  ${YELLOW}Some tests may have failed - check output above${NC}"
fi

# Done!
echo ""
echo -e "${GREEN}=== Setup Complete! ===${NC}"
echo ""
echo "Next steps:"
echo "  1. Activate the virtual environment:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Start the API server:"
echo "     python api_server.py"
echo ""
echo "  3. Open http://localhost:8000/docs for Swagger UI"
echo ""
echo "For more information, see README.md and CONTRIBUTING.md"
