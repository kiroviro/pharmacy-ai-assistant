"""E2E test configuration — adds tests/e2e/ to sys.path so bare 'from e2e_helpers' imports work."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
