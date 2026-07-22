"""Plug-and-play catalog bootstrap wrapper (see app/catalog/bootstrap.py).

Usage:
    python scripts/catalog_bootstrap.py --parent "<name>" --partnership "<name>" \
        --imports "/path/to/QB Summa Terra/Import_Files" [--dry-run]
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain script: ensure the project root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.catalog.bootstrap import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
