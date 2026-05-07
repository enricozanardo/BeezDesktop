"""App-level query state shared across view instances.

Why this exists
---------------
SmartView and KnowledgeView both spawn long-running worker threads
(RAG queries, marketplace queries) that take 5-30s to complete. After
v0.6.1, navigating away from those views during a query cancels the
asyncio task and `safe_ui_call` becomes a no-op, so the result is
silently dropped when the user returns. That is exactly the B-15
"query forgotten on navigation" symptom.

The fix: keep query state on the `app` instance. View instances are
short-lived and rebuilt on every navigation; the state lives forever.
Worker threads write to the state on completion (cheap dict updates,
GIL-protected). When a view is built, it reads the state and:

- "idle"    -> empty UI
- "running" -> show the in-flight query text + a "running..." status,
               and start a polling task tracked by ViewLifecycle that
               watches the state and updates UI when it transitions.
- "done"    -> render the cached answer/sources (no re-query needed).
- "error"   -> show the cached error message.

Everything is in-memory (no disk persistence) and resets on app
restart, which is what we want -- a fresh app should not auto-replay
yesterday's queries.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


_STATUSES = ("idle", "running", "done", "error")


@dataclass
class QueryState:
    """Mutable container for a single query's lifecycle.

    Attributes:
        status: One of ``idle | running | done | error``.
        query_text: The user-typed question (so build() can restore it
            into the input widget on view rebuild).
        result: Backend response dict on success, else None.
        error_msg: Human-readable error string on failure, else None.
        ts: time.time() of the last status change (for ordering).
        extra: Free-form payload (e.g. listing_id for knowledge queries
            so we can remember which listing was being queried).
    """

    status: str = "idle"
    query_text: str = ""
    result: Optional[Dict[str, Any]] = None
    error_msg: Optional[str] = None
    ts: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def begin(self, query_text: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Atomically transition to running."""
        with self._lock:
            self.status = "running"
            self.query_text = query_text
            self.result = None
            self.error_msg = None
            self.extra = dict(extra or {})
            self.ts = time.time()

    def succeed(self, result: Dict[str, Any]) -> None:
        with self._lock:
            self.status = "done"
            self.result = result
            self.error_msg = None
            self.ts = time.time()

    def fail(self, error_msg: str) -> None:
        with self._lock:
            self.status = "error"
            self.error_msg = error_msg
            self.ts = time.time()

    def clear(self) -> None:
        with self._lock:
            self.status = "idle"
            self.query_text = ""
            self.result = None
            self.error_msg = None
            self.extra = {}
            self.ts = time.time()

    def snapshot(self) -> Dict[str, Any]:
        """Return a thread-safe snapshot for read-only consumers."""
        with self._lock:
            return {
                "status": self.status,
                "query_text": self.query_text,
                "result": self.result,
                "error_msg": self.error_msg,
                "ts": self.ts,
                "extra": dict(self.extra),
            }


@dataclass
class KnowledgeBrowseState:
    """Persistent state for KnowledgeView.Browse + selection.

    Why this exists (B-18): when the user navigates away from
    KnowledgeView and comes back, the view is destroyed and re-built
    from scratch, so ``self.listings`` and ``self.selected_listing`` are
    re-initialised to empty/None and the user sees a blank Browse tab
    even though they had just searched and picked a listing. This
    matches the same root cause as B-15 for queries; the fix is the
    same -- park the data on ``app`` so it outlives the view instance.

    The state stores a *snapshot* of search results (a list of plain
    dicts), not view-level Toga widgets. The view rebuild reads this
    snapshot and re-populates its widgets, so we never need to re-hit
    the network.
    """

    listings: List[Dict[str, Any]] = field(default_factory=list)
    selected_listing: Optional[Dict[str, Any]] = None
    search_query: str = ""
    search_tags: str = ""
    active_tab: str = "browse"  # browse | query | publish | my_listings
    last_search_ts: float = 0.0

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set_listings(
        self,
        listings: List[Dict[str, Any]],
        *,
        search_query: str = "",
        search_tags: str = "",
    ) -> None:
        with self._lock:
            self.listings = list(listings or [])
            self.search_query = search_query
            self.search_tags = search_tags
            self.last_search_ts = time.time()

    def set_selected(self, listing: Optional[Dict[str, Any]]) -> None:
        with self._lock:
            self.selected_listing = dict(listing) if listing else None

    def set_active_tab(self, tab: str) -> None:
        with self._lock:
            self.active_tab = tab

    def clear(self) -> None:
        with self._lock:
            self.listings = []
            self.selected_listing = None
            self.search_query = ""
            self.search_tags = ""
            self.active_tab = "browse"
            self.last_search_ts = 0.0

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "listings": list(self.listings),
                "selected_listing": dict(self.selected_listing) if self.selected_listing else None,
                "search_query": self.search_query,
                "search_tags": self.search_tags,
                "active_tab": self.active_tab,
                "last_search_ts": self.last_search_ts,
            }


class AppQueryStates:
    """Holder for every view's persistent query state.

    Add new views here as needed. Each attribute is independent.
    """

    def __init__(self) -> None:
        self.smart = QueryState()
        self.knowledge = QueryState()
        # B-18: knowledge browse / selection survives view destruction.
        self.knowledge_browse = KnowledgeBrowseState()


def classify_smart_node_error(error_msg: str) -> str:
    """Translate a raw exception string to a user-facing reason.

    Returns one of:
        - "unreachable"  : connection/dns/refused/timeout
        - "not_found"    : 404 or "not found" / "no such listing"
        - "auth"         : 401/403/forbidden/unauthorized
        - "server"       : 5xx
        - "other"        : anything else
    """
    if not error_msg:
        return "other"
    lower = error_msg.lower()
    if any(tok in lower for tok in (
        "connection refused", "name or service",
        "max retries", "connectionerror", "timed out", "timeout",
        "no route to host",
    )):
        return "unreachable"
    if any(tok in lower for tok in (
        "404", "not found", "no such listing", "listing not found",
    )):
        return "not_found"
    if any(tok in lower for tok in (
        "401", "403", "unauthorized", "forbidden",
    )):
        return "auth"
    if any(tok in lower for tok in (
        "500", "502", "503", "504", "internal server",
    )):
        return "server"
    return "other"


def humanize_smart_node_error(error_msg: str, *, smart_node_label: str = "this smart node") -> str:
    """Map a raw error to the message we want to show the user.

    Specifically distinguishes "node is dead" from "node is up but
    doesn't have the listing", which was the B-15 confusion source.
    """
    kind = classify_smart_node_error(error_msg)
    if kind == "unreachable":
        return (
            f"[!] {smart_node_label} is unreachable. Pick another smart "
            "node above and try again."
        )
    if kind == "not_found":
        return (
            f"[!] This listing isn't available on {smart_node_label}. "
            "Marketplace data may not be replicated yet -- pick another "
            "smart node above and retry."
        )
    if kind == "auth":
        return f"[!] {smart_node_label} refused the request (auth). Contact support."
    if kind == "server":
        return f"[!] {smart_node_label} returned a server error. Try again or pick another."
    return f"Error: {error_msg}"
