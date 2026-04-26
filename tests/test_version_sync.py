"""Version-sync regression test.

`.cursor/rules/beez-rules.mdc` mandates that the BeezDesktop version is
identical in all three of:

  * BeezDesktop/src/beezdesktop/__init__.py     -> __version__
  * BeezDesktop/pyproject.toml                  -> [project] version
  * BeezDesktop/pyproject.toml                  -> [tool.briefcase] version

Past releases shipped with all three out of sync (0.4.0 vs 0.3.14 vs 0.3.14)
which made the running app misreport its build.  This test fails fast if
any one of them drifts again.
"""

from __future__ import annotations

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIT = os.path.join(ROOT, "src", "beezdesktop", "__init__.py")
PYPROJECT = os.path.join(ROOT, "pyproject.toml")


def _read_init_version() -> str:
    with open(INIT, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, f"__version__ assignment not found in {INIT}"
    return m.group(1)


def _read_pyproject_versions() -> tuple[str, str]:
    with open(PYPROJECT, "r", encoding="utf-8") as f:
        text = f.read()

    # [project] block.
    proj = re.search(
        r'\[project\][^\[]*?^version\s*=\s*"([^"]+)"',
        text,
        re.MULTILINE | re.DOTALL,
    )
    # [tool.briefcase] block.
    brief = re.search(
        r'\[tool\.briefcase\][^\[]*?^version\s*=\s*"([^"]+)"',
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert proj, f"[project] version not found in {PYPROJECT}"
    assert brief, f"[tool.briefcase] version not found in {PYPROJECT}"
    return proj.group(1), brief.group(1)


@pytest.mark.smoke
def test_versions_match_across_all_three_locations():
    init_v = _read_init_version()
    proj_v, brief_v = _read_pyproject_versions()

    assert init_v == proj_v == brief_v, (
        "BeezDesktop version drifted: "
        f"__init__.py={init_v!r} pyproject[project]={proj_v!r} "
        f"pyproject[briefcase]={brief_v!r}; "
        "see .cursor/rules/beez-rules.mdc -- all three MUST match."
    )
