"""Regression tests for B-15 (queries dropped on view navigation).

After v0.6.1 fixed the dead-widget mutation bug, a side-effect emerged:
``spawn_task``-tracked queries were cancelled on view destruction, and
worker threads' ``safe_ui_call`` callbacks became no-ops, so the result
of a long-running smart/knowledge query was silently dropped when the
user navigated away mid-query.

The fix moves query state to the app-level ``app.query_states`` so a
freshly-rebuilt view can read it back. These tests pin that contract.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "src", "shared"):
    p = os.path.join(ROOT, sub) if sub else ROOT
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)


from beezdesktop.query_state import (  # noqa: E402
    AppQueryStates,
    KnowledgeBrowseState,
    QueryState,
    classify_smart_node_error,
    humanize_smart_node_error,
)


def test_query_state_lifecycle_idle_to_done():
    qs = QueryState()
    assert qs.snapshot()["status"] == "idle"

    qs.begin("what is foo?", extra={"top_k": 5})
    snap = qs.snapshot()
    assert snap["status"] == "running"
    assert snap["query_text"] == "what is foo?"
    assert snap["extra"]["top_k"] == 5
    assert snap["result"] is None
    assert snap["error_msg"] is None

    qs.succeed({"answer": "42", "sources": []})
    snap = qs.snapshot()
    assert snap["status"] == "done"
    assert snap["result"] == {"answer": "42", "sources": []}


def test_query_state_lifecycle_idle_to_error():
    qs = QueryState()
    qs.begin("explode pls")
    qs.fail("Connection refused to smart node")
    snap = qs.snapshot()
    assert snap["status"] == "error"
    assert snap["error_msg"] == "Connection refused to smart node"
    assert snap["result"] is None


def test_query_state_clear_resets_to_idle():
    qs = QueryState()
    qs.begin("q")
    qs.succeed({"answer": "a"})
    qs.clear()
    assert qs.snapshot()["status"] == "idle"
    assert qs.snapshot()["result"] is None
    assert qs.snapshot()["query_text"] == ""


def test_app_query_states_holds_smart_and_knowledge():
    """B-15 contract: both views must have independent state."""
    s = AppQueryStates()
    assert isinstance(s.smart, QueryState)
    assert isinstance(s.knowledge, QueryState)
    s.smart.begin("smart q")
    s.knowledge.begin("knowledge q")
    assert s.smart.snapshot()["query_text"] == "smart q"
    assert s.knowledge.snapshot()["query_text"] == "knowledge q"


def test_query_state_thread_safe_under_concurrent_writers():
    """begin/succeed/fail must not corrupt state under threads."""
    import threading
    qs = QueryState()
    errors: list = []

    def writer(i: int):
        try:
            qs.begin(f"q{i}")
            qs.succeed({"answer": f"a{i}"})
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(2.0)

    assert not errors, f"writers raised: {errors}"
    snap = qs.snapshot()
    assert snap["status"] == "done"
    # Last writer wins; that's the contract.


# ----------------------------------------------------------------------
# B-15 main scenario: result survives view destruction
# ----------------------------------------------------------------------

def test_worker_completion_after_view_destroy_persists_to_state():
    """The exact scenario the user reported.

    1. User opens Smart / clicks Ask.
    2. Worker thread starts long RAG round-trip.
    3. User navigates to Files (view destroyed).
    4. Worker completes; safe_ui_call no-ops on dead view.
    5. User navigates back to Smart.
    6. New SmartView reads app.query_states.smart.snapshot()
       and finds status="done" with the result -> displays it.

    This test simulates step 1-4 and asserts state survives.
    """
    from beezdesktop.views.lifecycle import ViewLifecycle

    class _FakeLoop:
        def __init__(self):
            self.scheduled = []

        def call_soon_threadsafe(self, cb, *args):
            self.scheduled.append(cb)

    class _FakeApp:
        def __init__(self):
            self.loop = _FakeLoop()
            self.query_states = AppQueryStates()

    app = _FakeApp()
    view = ViewLifecycle(app)
    qstate = app.query_states.smart

    # Step 1: user clicks Ask.
    qstate.begin("what is BeezDirectory?")
    assert qstate.snapshot()["status"] == "running"

    # Step 2-3: simulate navigation while worker is mid-flight.
    view.destroy()

    # Step 4: worker completes AFTER destroy and writes state.
    qstate.succeed({"answer": "Beez consensus coordinator", "sources": []})

    # Step 5-6: a fresh view (rebuilt from navigation back) can find it.
    snap = qstate.snapshot()
    assert snap["status"] == "done"
    assert snap["query_text"] == "what is BeezDirectory?"
    assert snap["result"]["answer"] == "Beez consensus coordinator"


# ----------------------------------------------------------------------
# B-15 secondary: error classifier (the "unreachable" misnomer fix)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("err,expected", [
    ("HTTPConnectionPool: Max retries exceeded", "unreachable"),
    ("Connection refused", "unreachable"),
    ("Read timed out after 30s", "unreachable"),
    ("Name or service not known", "unreachable"),
    ("404 Not Found", "not_found"),
    ("listing not found", "not_found"),
    ("403 Forbidden", "auth"),
    ("Unauthorized", "auth"),
    ("500 Internal Server Error", "server"),
    ("502 Bad Gateway", "server"),
    ("something weird happened", "other"),
    ("", "other"),
])
def test_classify_smart_node_error(err: str, expected: str):
    assert classify_smart_node_error(err) == expected


def test_humanize_distinguishes_unreachable_from_not_found():
    """B-15 root: a 404 must not be reported as 'unreachable'."""
    msg = humanize_smart_node_error("404 Not Found", smart_node_label="smart1")
    assert "isn't available" in msg or "not available" in msg
    assert "unreachable" not in msg.lower()

    msg2 = humanize_smart_node_error("Connection refused", smart_node_label="smart1")
    assert "unreachable" in msg2.lower()


# ----------------------------------------------------------------------
# B-18: KnowledgeBrowseState (browse listings + selection survive nav)
# ----------------------------------------------------------------------


def test_knowledge_browse_state_default_empty():
    s = KnowledgeBrowseState()
    snap = s.snapshot()
    assert snap["listings"] == []
    assert snap["selected_listing"] is None
    assert snap["search_query"] == ""
    assert snap["search_tags"] == ""
    assert snap["active_tab"] == "browse"


def test_knowledge_browse_state_set_listings_persists():
    s = KnowledgeBrowseState()
    listings = [
        {"listing_id": "L1", "title": "Limen-AI", "price_per_query": 0.5},
        {"listing_id": "L2", "title": "Other", "price_per_query": 1.0},
    ]
    s.set_listings(listings, search_query="ai", search_tags="rag,llm")

    snap = s.snapshot()
    assert len(snap["listings"]) == 2
    assert snap["listings"][0]["listing_id"] == "L1"
    assert snap["search_query"] == "ai"
    assert snap["search_tags"] == "rag,llm"
    assert snap["last_search_ts"] > 0


def test_knowledge_browse_state_set_listings_is_independent_copy():
    """Mutating the original list must not mutate persisted state."""
    s = KnowledgeBrowseState()
    src = [{"listing_id": "L1", "title": "A"}]
    s.set_listings(src)
    src.append({"listing_id": "L2", "title": "Late"})
    snap = s.snapshot()
    assert len(snap["listings"]) == 1
    assert snap["listings"][0]["listing_id"] == "L1"


def test_knowledge_browse_state_set_selected_persists():
    s = KnowledgeBrowseState()
    s.set_selected({"listing_id": "L1", "title": "Limen-AI"})
    snap = s.snapshot()
    assert snap["selected_listing"]["listing_id"] == "L1"
    assert snap["selected_listing"]["title"] == "Limen-AI"


def test_knowledge_browse_state_clear_selected():
    s = KnowledgeBrowseState()
    s.set_selected({"listing_id": "L1"})
    s.set_selected(None)
    assert s.snapshot()["selected_listing"] is None


def test_knowledge_browse_state_set_active_tab():
    s = KnowledgeBrowseState()
    for tab in ("query", "publish", "my_listings", "browse"):
        s.set_active_tab(tab)
        assert s.snapshot()["active_tab"] == tab


def test_knowledge_browse_state_clear_resets_everything():
    s = KnowledgeBrowseState()
    s.set_listings(
        [{"listing_id": "L1"}],
        search_query="q",
        search_tags="t",
    )
    s.set_selected({"listing_id": "L1"})
    s.set_active_tab("query")
    s.clear()

    snap = s.snapshot()
    assert snap["listings"] == []
    assert snap["selected_listing"] is None
    assert snap["search_query"] == ""
    assert snap["search_tags"] == ""
    assert snap["active_tab"] == "browse"


def test_app_query_states_holds_knowledge_browse_state():
    states = AppQueryStates()
    assert isinstance(states.knowledge_browse, KnowledgeBrowseState)
    # Independent from the other slots.
    states.knowledge_browse.set_active_tab("query")
    assert states.knowledge.snapshot()["status"] == "idle"
    assert states.smart.snapshot()["status"] == "idle"


def test_b18_simulation_navigate_away_and_back():
    """End-to-end B-18 simulation.

    1. View 1 of KnowledgeView searches the marketplace and gets results.
    2. User selects a listing.
    3. User navigates away. View 1 destroyed.
    4. User comes back. A fresh View 2 reads the persisted state.
    5. View 2's listings + selection match what View 1 had, so the
       Browse table is not blank and the user can resume immediately.
    """
    states = AppQueryStates()

    # Step 1+2: View 1 stores its findings.
    listings = [
        {"listing_id": "L1", "title": "Limen-AI", "price_per_query": 0},
        {"listing_id": "L2", "title": "Cooking-RAG", "price_per_query": 0.5},
    ]
    states.knowledge_browse.set_listings(listings, search_query="ai")
    states.knowledge_browse.set_selected(listings[0])
    states.knowledge_browse.set_active_tab("query")

    # Step 3+4: imagine View 1 is gone; View 2 reads the snapshot.
    snap = states.knowledge_browse.snapshot()

    # Step 5: View 2 has everything it needs, no network re-hit.
    assert len(snap["listings"]) == 2
    assert snap["listings"][0]["title"] == "Limen-AI"
    assert snap["selected_listing"]["listing_id"] == "L1"
    assert snap["active_tab"] == "query"
    assert snap["search_query"] == "ai"
