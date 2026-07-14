# Ensures the repo root (and thus the `benchmark` package) is importable
# when pytest runs against the installed `yoda` package, e.g. in CI.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
