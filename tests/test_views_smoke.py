"""Import smoke tests for BeezDesktop view modules.

We can't construct real Toga widgets in headless CI (no display, no
backend), but we *can* prove that every view module imports cleanly and
exposes the class BeezDesktop expects.  This catches:

  - syntax errors that ship to a Briefcase bundle
  - circular imports between views
  - removed/renamed view classes that would crash the app at startup

Toga is required to import the views (they `import toga` at the top).
The CI workflow installs `toga toga-dummy` and exports
``TOGA_BACKEND=toga_dummy`` so these tests run headless.  Locally, if
toga is not installed, we skip rather than fail.
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest

toga = pytest.importorskip("toga")  # noqa: F841 -- needed for view imports

# Bootstrap sys.path the same way conftest.py does.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("", "src", "shared"):
    p = os.path.join(ROOT, sub) if sub else ROOT
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)


VIEW_MODULES = [
    ("beezdesktop.views.files", "FilesView"),
    ("beezdesktop.views.knowledge", "KnowledgeView"),
    ("beezdesktop.views.smart", None),  # may not export a single class
    ("beezdesktop.views.settings", None),
    ("beezdesktop.views.transactions", None),
    ("beezdesktop.views.blockchain", None),
    ("beezdesktop.views.wallet", None),
    ("beezdesktop.views.network", None),
    ("beezdesktop.views.dashboard", None),
]


@pytest.mark.parametrize("module_name,expected_class", VIEW_MODULES)
def test_view_module_imports(module_name, expected_class):
    """Every view module must import cleanly without a running Toga app."""
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:
        pytest.fail(f"View module {module_name!r} failed to import: {exc!r}")
    if expected_class:
        assert hasattr(mod, expected_class), (
            f"Module {module_name} no longer exports {expected_class}; "
            "BeezDesktop's main_app.py constructs this class by name."
        )


def test_knowledge_view_get_smart_url_no_localhost_fallback():
    """The localhost fallback was a production bug masking missing nodes."""
    from beezdesktop.views import knowledge as kv

    class _Stub(kv.KnowledgeView.__mro__[0]):
        def __init__(self):
            self.selected_smart_node = None

    stub = _Stub.__new__(kv.KnowledgeView)
    stub.selected_smart_node = None
    assert kv.KnowledgeView._get_smart_url(stub) == "", (
        "_get_smart_url must return empty string when no node is selected; "
        "the old localhost:5000 fallback hid production failures."
    )

    stub.selected_smart_node = {"ip": ""}
    assert kv.KnowledgeView._get_smart_url(stub) == ""

    stub.selected_smart_node = {"ip": "203.0.113.42"}
    url = kv.KnowledgeView._get_smart_url(stub)
    assert url.startswith("http://203.0.113.42"), url
    assert "localhost" not in url
    assert "127.0.0.1" not in url
