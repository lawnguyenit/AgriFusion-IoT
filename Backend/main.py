"""Deprecated shim: the telemetry CLI is now ``agrifusion`` (``python -m agrifusion``).

Kept only so ``python -m Backend.main ...`` keeps working for now; it will be removed.
"""
from __future__ import annotations

import warnings

from agrifusion.cli import main

__all__ = ["main"]

if __name__ == "__main__":
    warnings.warn(
        "`python -m Backend.main` is deprecated; use `agrifusion` or `python -m agrifusion`.",
        DeprecationWarning,
        stacklevel=1,
    )
    main()
