"""Regenerate the golden snapshot. Run from the repo root:

    python Backend/tests/golden/data_chain/update_golden.py

Review `git diff Backend/tests/golden/data_chain/expected` before committing.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from Backend.tests.golden_chain_support import run_chain, snapshot, write_expected  # noqa: E402

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp_dir:
        backend_dir = Path(temp_dir)
        run_chain(backend_dir)
        files = snapshot(backend_dir)
    write_expected(files)
    print(f"wrote {len(files)} golden files")
