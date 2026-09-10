"""Single source of truth for on-disk locations.

Modules live at varying depths under ``core/`` and ``approaches/``, so anchoring
data, cache and results directories to ``__file__`` breaks whenever a module
moves. Everything resolves through here instead.
"""

import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(REPO_ROOT, "data")
RESULTS_DIR = os.path.join(REPO_ROOT, "results")
CACHE_DIR = os.path.join(REPO_ROOT, ".cache")

__all__ = ["REPO_ROOT", "DATA_DIR", "RESULTS_DIR", "CACHE_DIR"]
