from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

for relative in (
    "packages/py-core/src",
    "packages/py-evals/src",
    "packages/py-agents/src",
    "apps/cli/src",
):
    sys.path.insert(0, str(ROOT / relative))
