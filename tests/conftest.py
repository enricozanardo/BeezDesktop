"""Test bootstrap for BeezDesktop unit tests.

Adds the project's `shared/` and `src/` paths to sys.path so we can import
`shared.client_core.*` and `beezdesktop.*` directly without installing the
briefcase package.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))

for sub in ("", "src", "shared"):
    p = os.path.join(ROOT, sub) if sub else ROOT
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)
