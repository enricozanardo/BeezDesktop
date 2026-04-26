#!/usr/bin/env bash
# BeezDesktop/scripts/release.sh -- one-command BeezDesktop release.
#
# This is the source of truth for cutting a BeezDesktop release.  It lives
# inside BeezDesktop/ (the repo it releases from) so a contributor can clone
# just BeezDesktop and ship a new version without checking out the umbrella
# BeezMaster monorepo.
#
# What it does (in order):
#   1. (Optional) Rewrite the version in the THREE source-of-truth files when
#      --version X.Y.Z is given (per .cursor/rules/beez-rules.mdc).
#   2. Verify the three values are identical.
#   3. Verify the tag does not already exist locally or on the remote.
#   4. Run `pytest tests/` under TOGA_BACKEND=toga_dummy unless --skip-tests.
#   5. Show the shared submodule status and abort if it has internal
#      uncommitted changes (those must be released as BeezShared first).
#   6. Stage every modified path including the submodule pointer, commit
#      with "Release vX.Y.Z" (skipped if working tree is already clean).
#   7. Create the annotated tag vX.Y.Z.
#   8. Push the current branch + tag to <remote> (default origin) unless
#      --no-push.  The push triggers .github/workflows/build.yml which
#      builds Linux / macOS / Windows artifacts and opens a GitHub Release.
#
# Usage:
#   scripts/release.sh                       # release at current version
#   scripts/release.sh --version 0.5.0       # bump + release
#   scripts/release.sh --dry-run             # show what would happen
#   scripts/release.sh --no-push             # local commit + tag, no push
#   scripts/release.sh --skip-tests          # only for documented hotfixes
#   scripts/release.sh --remote upstream     # push to a non-origin remote
#   scripts/release.sh --allow-dirty-shared  # ignore submodule dirty check
#
# Exit codes:
#   0  release succeeded (commit + tag created; pushed unless --no-push)
#   1  precondition failure (version drift, tag exists, shared dirty, ...)
#   2  pytest is red
#  64  bad CLI argument

set -euo pipefail

DRY_RUN=false
NO_PUSH=false
SKIP_TESTS=false
ALLOW_DIRTY_SHARED=false
REMOTE=origin
NEW_VERSION=""

usage() { sed -n '2,40p' "$0" | sed 's/^# \?//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)              NEW_VERSION="$2"; shift ;;
        --dry-run)              DRY_RUN=true ;;
        --no-push)              NO_PUSH=true ;;
        --skip-tests)           SKIP_TESTS=true ;;
        --allow-dirty-shared)   ALLOW_DIRTY_SHARED=true ;;
        --remote)               REMOTE="$2"; shift ;;
        -h|--help)              usage; exit 0 ;;
        *) echo "[FATAL] unknown arg: $1" >&2; exit 64 ;;
    esac
    shift
done

run() {
    if $DRY_RUN; then
        printf '[dry-run] '; printf '%q ' "$@"; printf '\n'
    else
        printf '+ '; printf '%q ' "$@"; printf '\n'
        "$@"
    fi
}

DESKTOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DESKTOP_DIR"

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "[FAIL] $DESKTOP_DIR is not a git repository." >&2
    exit 1
fi

INIT_FILE="src/beezdesktop/__init__.py"
PYPROJECT="pyproject.toml"
DIST_META="src/beezdesktop.dist-info/METADATA"

# ---- 1. optional version rewrite --------------------------------------------
if [[ -n "$NEW_VERSION" ]]; then
    echo "[release] bumping version to $NEW_VERSION"
    if $DRY_RUN; then
        echo "[dry-run] would rewrite __init__.py + pyproject.toml ([project] + [tool.briefcase])"
        [[ -f "$DIST_META" ]] && echo "[dry-run] would rewrite $DIST_META"
    else
        sed -i "s/^__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" "$INIT_FILE"
        # Section-aware rewrite for the two `version =` lines in pyproject.toml.
        awk -v v="$NEW_VERSION" '
            /^\[/ { section=$0 }
            section ~ /^\[project\]$/ && /^version = / { sub(/".*"/, "\""v"\"") }
            section ~ /^\[tool\.briefcase\]$/ && /^version = / { sub(/".*"/, "\""v"\"") }
            { print }
        ' "$PYPROJECT" >"$PYPROJECT.tmp" && mv "$PYPROJECT.tmp" "$PYPROJECT"
        if [[ -f "$DIST_META" ]]; then
            sed -i "s/^Version: .*/Version: $NEW_VERSION/" "$DIST_META"
        fi
    fi
fi

# ---- 2. verify version sync -------------------------------------------------
init_v=$(grep -E '^__version__' "$INIT_FILE" | head -1 | cut -d'"' -f2)
proj_v=$(awk '/^\[project\]/{flag=1;next}/^\[/{flag=0}flag && /^version =/' \
            "$PYPROJECT" | head -1 | cut -d'"' -f2)
brief_v=$(awk '/^\[tool\.briefcase\]/{flag=1;next}/^\[/{flag=0}flag && /^version =/' \
             "$PYPROJECT" | head -1 | cut -d'"' -f2)

echo "============================================"
echo "  BeezDesktop release"
echo "============================================"
echo "  __init__.py        : $init_v"
echo "  pyproject [project]: $proj_v"
echo "  pyproject briefcase: $brief_v"

if [[ -z "$init_v" || "$init_v" != "$proj_v" || "$proj_v" != "$brief_v" ]]; then
    cat <<EOF >&2
[FAIL] BeezDesktop version is desynced.
       beez-rules.mdc requires the version to match in all three locations:
         $INIT_FILE                 -> __version__
         $PYPROJECT [project] section
         $PYPROJECT [tool.briefcase] section
       Re-run with --version X.Y.Z to fix in one shot.
EOF
    exit 1
fi

VERSION="$init_v"
TAG="v$VERSION"

# ---- 3. tag must not already exist ------------------------------------------
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    echo "[FAIL] local tag $TAG already exists; bump --version first." >&2
    exit 1
fi
if git ls-remote --tags "$REMOTE" "$TAG" 2>/dev/null | grep -q "refs/tags/$TAG"; then
    echo "[FAIL] remote tag $TAG already exists on $REMOTE; bump --version first." >&2
    exit 1
fi

# ---- 4. tests ---------------------------------------------------------------
if $SKIP_TESTS; then
    echo "[release] skipping tests (--skip-tests)"
else
    # Distinguish "pytest not installed" from "tests actually failed".
    if ! python3 -c "import pytest" 2>/dev/null; then
        cat <<EOF >&2
[FAIL] pytest is not installed in this Python environment.
       This is NOT a test failure -- the test runner is missing.

       Install the BeezDesktop test extras and re-run:
         pip install -e ".[test]"
       or
         pip install pytest pytest-timeout toga-core toga-dummy

       To skip tests entirely (only for documented hotfixes):
         scripts/release.sh --skip-tests $*
EOF
        exit 1
    fi
    if ! python3 -c "import toga" 2>/dev/null; then
        cat <<EOF >&2
[FAIL] toga is not installed in this Python environment.
       The view smoke tests import toga.  Install:
         pip install -e ".[test]"
       or
         pip install toga-core toga-dummy
EOF
        exit 1
    fi
    echo "[release] running pytest tests/ (TOGA_BACKEND=toga_dummy)"
    if ! TOGA_BACKEND=toga_dummy python3 -m pytest -q tests/ --maxfail=1; then
        echo "[FAIL] BeezDesktop tests are red; refusing to release." >&2
        exit 2
    fi
fi

# ---- 5. submodule sanity ----------------------------------------------------
if [[ -d shared/.git || -f shared/.git ]]; then
    if [[ -n "$(git -C shared status --porcelain 2>/dev/null)" ]]; then
        if $ALLOW_DIRTY_SHARED; then
            echo "[release] WARN: shared/ has uncommitted changes; --allow-dirty-shared set."
            echo "         The release will pin the CURRENT shared SHA, which still"
            echo "         points at the last shared commit -- internal edits will NOT ship."
        else
            cat <<EOF >&2
[FAIL] shared/ submodule has uncommitted changes:
$(git -C shared status --short | sed 's/^/  /')

These belong to BeezShared, not BeezDesktop.  Release them there first:
  cd shared/
  git add -A && git commit -m "..." && git push
  cd ..
  git add shared && git commit -m "Bump BeezShared pointer"

Or pass --allow-dirty-shared to ignore (the current shared SHA will be
pinned and your local edits will NOT be in the build).
EOF
            exit 1
        fi
    fi
fi

# ---- 6. stage + commit if dirty ---------------------------------------------
if [[ -n "$(git status --porcelain)" ]]; then
    echo "[release] staging working tree for commit"
    run git add -A
    run git commit -m "Release $TAG"
else
    echo "[release] working tree is clean -- tagging existing HEAD"
fi

# ---- 7. annotated tag -------------------------------------------------------
run git tag -a "$TAG" -m "BeezDesktop $TAG"

# ---- 8. push ----------------------------------------------------------------
BRANCH="$(git branch --show-current)"
if $NO_PUSH; then
    echo
    echo "[release] --no-push set.  To finish manually:"
    echo "    git push $REMOTE $BRANCH"
    echo "    git push $REMOTE $TAG"
    exit 0
fi

run git push "$REMOTE" "$BRANCH"
run git push "$REMOTE" "$TAG"

remote_url="$(git remote get-url "$REMOTE" 2>/dev/null \
                | sed -e 's,\.git$,,' -e 's,^git@\([^:]*\):,https://\1/,' || echo '')"

echo
echo "============================================"
echo "  Released BeezDesktop $TAG"
echo "============================================"
if [[ -n "$remote_url" ]]; then
    echo "  Watch the build matrix at:"
    echo "    $remote_url/actions"
    echo "  Release artifacts will appear at:"
    echo "    $remote_url/releases/tag/$TAG"
fi
