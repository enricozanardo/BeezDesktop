"""
Knowledge Marketplace View

Provides a UI for the knowledge marketplace:
- Browse/search published knowledge collections
- Query a listing (pay-per-query, answers only)
- Publish your own indexed files as a knowledge listing
- Manage your listings (edit, pause, unpublish)
- Purchase full ownership of a listing
"""

import logging
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import threading
import hashlib

from shared.client_core.encryption import derive_encryption_key
from beezdesktop.theme import Colors, Font, Spacing, page_header, LoadingIndicator
from beezdesktop.views.lifecycle import ViewLifecycle

logger = logging.getLogger("beezdesktop.knowledge")

# Tight timeout for marketplace metadata calls. The previous default of 30s
# left the loading indicator and `_busy` flag set for the full 30s whenever
# a smart node was unreachable, blocking every subsequent click.
_MARKETPLACE_TIMEOUT_S = 8

# Module-level fastembed cache. Loaded once via `prewarm_embed_model()` and
# read-only thereafter, so subsequent queries don't need to acquire a lock.
_embed_model = None
_embed_warm_lock = threading.Lock()
_embed_warm_started = False


def prewarm_embed_model() -> None:
    """Load the fastembed model in the calling thread (idempotent).

    Designed to be invoked from a daemon thread so the ~33MB BAAI ONNX
    download / unpack does not block the Toga main loop. Subsequent calls
    return immediately. Failures are logged and re-raised in `_get_embed_model`.
    """
    global _embed_model, _embed_warm_started
    with _embed_warm_lock:
        if _embed_model is not None:
            return
        if _embed_warm_started:
            # Another thread is already warming; wait until it finishes.
            pass
        _embed_warm_started = True
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding("BAAI/bge-small-en-v1.5")
    except ImportError as exc:
        logger.error("[KNOWLEDGE] fastembed unavailable: %s", exc)
        with _embed_warm_lock:
            _embed_warm_started = False
        return
    except Exception as exc:
        logger.error("[KNOWLEDGE] fastembed warm-up failed: %s", exc)
        with _embed_warm_lock:
            _embed_warm_started = False
        return
    with _embed_warm_lock:
        _embed_model = model
    logger.info("[KNOWLEDGE] fastembed model warmed up")


def _get_embed_model():
    """Return the warmed model or raise if it failed to load."""
    global _embed_model
    if _embed_model is not None:
        return _embed_model
    # Synchronous fallback if the user fired a query before the background
    # warm-up completed. This still blocks the calling worker thread (not
    # the UI), which is acceptable for the first query.
    prewarm_embed_model()
    if _embed_model is None:
        raise RuntimeError(
            "fastembed is required for knowledge queries. "
            "Install with: pip install fastembed"
        )
    return _embed_model


class KnowledgeView(ViewLifecycle):
    """Knowledge marketplace interface."""

    def __init__(self, app):
        ViewLifecycle.__init__(self, app)
        self.selected_smart_node = None
        self.smart_nodes = []
        self.listings = []
        self.my_listings = []
        self.selected_listing = None
        self._selected_listing_idx = -1
        self._reachability_label = None
        self._has_warned_unreachable = False

    def build(self) -> toga.Box:
        """Build the knowledge marketplace view."""
        self._busy = False
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        container.add(page_header("Knowledge Marketplace", "Buy, sell, and query knowledge collections powered by RAG"))

        try:
            if not self.app.client or not self.app.client.is_wallet_connected():
                container.add(toga.Label(
                    "Please connect a wallet first.",
                    style=Pack(padding=Spacing.XL, font_size=Font.SIZE_BODY, color=Colors.STATUS_OFFLINE),
                ))
                return container
        except Exception:
            container.add(toga.Label(
                "Wallet not available.",
                style=Pack(padding=Spacing.XL, font_size=Font.SIZE_BODY, color=Colors.STATUS_OFFLINE),
            ))
            return container

        try:
            # Smart node selector
            container.add(self._build_node_selector())

            # Reachability banner (hidden until a worker reports a connection error)
            self._reachability_label = toga.Label(
                "",
                style=Pack(
                    padding=(Spacing.XS, 0),
                    font_size=Font.SIZE_SMALL,
                    color=Colors.STATUS_OFFLINE,
                ),
            )
            container.add(self._reachability_label)

            # Tab row for Browse / Query / Publish / My Listings
            container.add(self._build_tab_bar())

            # Loading indicator (shared across all tabs)
            self._loading = LoadingIndicator("Loading...")
            container.add(self._loading.box)

            # Content area (changes based on tab)
            self.tab_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
            container.add(self.tab_content)

            # Status bar
            self.status_label = toga.Label(
                "",
                style=Pack(padding=(5, 0), font_size=10, color="#666666"),
            )
            container.add(self.status_label)

            # Load smart nodes (in-memory)
            self._load_smart_nodes()

            # B-18: rehydrate cached listings + selection from app state
            # BEFORE we open any tab so all tab handlers see the same
            # in-memory snapshot the user had before navigating away.
            self._rehydrate_browse_state_into_view()

            # B-18: re-open the tab the user left off on. Default is
            # Browse the very first time the view is built.
            try:
                last_tab = self.app.query_states.knowledge_browse.snapshot().get(
                    "active_tab", "browse"
                )
            except Exception:
                last_tab = "browse"
            tab_dispatcher = {
                "browse": self._show_browse_tab,
                "query": self._show_query_tab,
                "publish": self._show_publish_tab,
                "my_listings": self._show_my_listings_tab,
            }
            (tab_dispatcher.get(last_tab) or self._show_browse_tab)(None)

            # Warm up fastembed model in the background once Knowledge is opened
            # for the first time. Subsequent queries skip the heavy load.
            self._kick_off_fastembed_warmup()
        except Exception as e:
            logger.error(f"[KNOWLEDGE] Error building view: {e}")
            import traceback
            traceback.print_exc()
            container.add(toga.Label(
                f"Error loading Knowledge view: {e}",
                style=Pack(padding=Spacing.XL, font_size=Font.SIZE_BODY, color=Colors.STATUS_OFFLINE),
            ))

        return container

    def _set_busy(self, busy: bool, message: str = "Loading..."):
        """Show/hide the loading indicator and disable interaction."""
        self._busy = busy
        try:
            if busy:
                self._loading.show(message)
            else:
                self._loading.hide()
        except Exception:
            pass

    def _rehydrate_browse_state_into_view(self) -> None:
        """B-18: copy persisted browse state from app onto this view.

        We only restore the python-level data here (``self.listings``,
        ``self.selected_listing``, ``self._selected_listing_idx``). The
        actual widget population happens later, inside whichever tab
        builder runs (``_show_browse_tab`` re-renders the table,
        ``_show_query_tab`` re-populates the listing selector).
        """
        try:
            snap = self.app.query_states.knowledge_browse.snapshot()
        except Exception:
            return

        cached_listings = snap.get("listings") or []
        if cached_listings:
            self.listings = list(cached_listings)

        cached_sel = snap.get("selected_listing")
        if cached_sel and self.listings:
            target_id = cached_sel.get("listing_id")
            for i, ls in enumerate(self.listings):
                if ls.get("listing_id") == target_id:
                    self._selected_listing_idx = i
                    self.selected_listing = self.listings[i]
                    break

    # === UI Builders ===

    def _build_node_selector(self) -> toga.Box:
        """Build smart node selection row."""
        box = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))

        box.add(toga.Label("Smart Node", style=Pack(padding=(5, 10, 0, 0), font_weight="bold")))

        self.node_select = toga.Selection(
            items=["Loading..."],
            on_change=self._on_node_selected,
            style=Pack(flex=1, padding_right=10),
        )
        box.add(self.node_select)

        self.node_info_label = toga.Label(
            "", style=Pack(padding=(5, 0), font_size=10, color="#666666")
        )
        box.add(self.node_info_label)
        return box

    def _build_tab_bar(self) -> toga.Box:
        """Build the tab switching bar."""
        bar = toga.Box(style=Pack(direction=ROW, padding=(0, 0, Spacing.MD, 0)))
        tabs = [
            ("Browse", self._show_browse_tab),
            ("Query", self._show_query_tab),
            ("Publish", self._show_publish_tab),
            ("My Listings", self._show_my_listings_tab),
        ]
        for label, handler in tabs:
            btn = toga.Button(
                label,
                on_press=handler,
                style=Pack(
                    padding=(Spacing.SM, Spacing.XS),
                    width=120,
                    background_color=Colors.BG_HEADER,
                    color=Colors.TEXT_PRIMARY,
                    font_size=Font.SIZE_BODY,
                ),
            )
            bar.add(btn)
        return bar

    # === Tab Content Builders ===

    def _show_browse_tab(self, widget):
        """Show the Browse Marketplace tab."""
        try:
            self.tab_content.clear()
        except Exception:
            return
        # B-18: remember which tab is active so the next view rebuild
        # opens to the same place the user left off.
        try:
            self.app.query_states.knowledge_browse.set_active_tab("browse")
        except Exception:
            pass
        box = toga.Box(style=Pack(direction=COLUMN))

        # B-18: restore previously persisted search inputs so the user
        # sees the same query they ran before navigating away.
        snap = {}
        try:
            snap = self.app.query_states.knowledge_browse.snapshot()
        except Exception:
            snap = {}

        # Search row
        search_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        self.search_input = toga.TextInput(
            placeholder="Search knowledge collections...",
            style=Pack(flex=1, padding_right=10),
        )
        try:
            self.search_input.value = snap.get("search_query", "") or ""
        except Exception:
            pass
        search_row.add(self.search_input)

        self.tag_input = toga.TextInput(
            placeholder="Tags (comma-separated)",
            style=Pack(width=180, padding_right=10),
        )
        try:
            self.tag_input.value = snap.get("search_tags", "") or ""
        except Exception:
            pass
        search_row.add(self.tag_input)

        search_btn = toga.Button(
            "Search",
            on_press=self._on_search,
            style=Pack(padding=5, width=80, background_color="#0d6efd", color="#ffffff"),
        )
        search_row.add(search_btn)
        box.add(search_row)

        # Results table
        self.browse_table = toga.Table(
            headings=["Title", "Seller", "BZT/Query", "Buy Price", "Chunks", "Queries"],
            on_select=self._on_browse_select,
            style=Pack(height=200, padding=(5, 0)),
        )
        box.add(self.browse_table)
        self._browse_listing_ids: list = []

        # Detail + action row
        detail_row = toga.Box(style=Pack(direction=ROW, padding=(10, 0)))

        self.listing_detail_label = toga.Label(
            "Select a listing to see details",
            style=Pack(flex=1, font_size=11, color="#444444"),
        )
        detail_row.add(self.listing_detail_label)

        self.query_listing_btn = toga.Button(
            "Query This",
            on_press=self._on_query_listing_from_browse,
            style=Pack(padding=5, width=100, background_color="#0d6efd", color="#ffffff"),
            enabled=False,
        )
        detail_row.add(self.query_listing_btn)

        self.buy_listing_btn = toga.Button(
            "Purchase",
            on_press=self._on_purchase_listing,
            style=Pack(padding=5, width=100, background_color="#198754", color="#ffffff"),
            enabled=False,
        )
        detail_row.add(self.buy_listing_btn)

        box.add(detail_row)
        self.tab_content.add(box)

        # B-18: replay cached listings into the freshly built widgets.
        # ``self.listings`` was already restored from app state by
        # ``_rehydrate_browse_state_into_view`` in build(). Here we
        # only need to push them into the table and re-render the
        # selection details.
        if self.listings:
            self._render_browse_table_from_listings()
            self.status_label.text = (
                f"Restored {len(self.listings)} cached listings "
                "(click Search to refresh)."
            )

        if self.selected_listing:
            listing = self.selected_listing
            desc = listing.get("description", "")[:120]
            tags = ", ".join(listing.get("tags", []))
            try:
                self.listing_detail_label.text = (
                    f"{desc}{'...' if len(listing.get('description', '')) > 120 else ''}"
                    f" | Tags: {tags or 'none'}"
                )
                self.query_listing_btn.enabled = True
                pp = float(listing.get("purchase_price", 0))
                is_own = False
                try:
                    wallet = self.app.client.get_current_wallet()
                    if wallet and listing.get("seller_address") == wallet.address:
                        is_own = True
                except Exception:
                    pass
                self.buy_listing_btn.enabled = pp > 0 and not is_own
            except Exception:
                pass

    def _show_query_tab(self, widget):
        """Show the Query a Listing tab."""
        try:
            self.tab_content.clear()
        except Exception:
            return
        # B-18: persist active tab.
        try:
            self.app.query_states.knowledge_browse.set_active_tab("query")
        except Exception:
            pass
        box = toga.Box(style=Pack(direction=COLUMN))

        # Listing selector
        ls_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        ls_row.add(toga.Label("Listing", style=Pack(padding=(5, 10, 0, 0), font_weight="bold")))
        self.query_listing_select = toga.Selection(
            items=["Search listings first..."],
            on_change=self._on_query_listing_changed,
            style=Pack(flex=1),
        )
        ls_row.add(self.query_listing_select)
        box.add(ls_row)

        self.query_listing_info = toga.Label(
            "", style=Pack(padding=(0, 0, 5, 0), font_size=10, color="#666666")
        )
        box.add(self.query_listing_info)

        # Query input
        box.add(toga.Label("Ask a Question", style=Pack(padding=(10, 0, 5, 0), font_weight="bold")))
        self.query_input = toga.MultilineTextInput(
            placeholder="Ask a question about this knowledge collection...",
            style=Pack(height=80, padding=(0, 0, 10, 0)),
        )
        box.add(self.query_input)

        q_row = toga.Box(style=Pack(direction=ROW))
        q_row.add(toga.Box(style=Pack(flex=1)))
        self.ask_btn = toga.Button(
            "Ask",
            on_press=self._on_marketplace_query,
            style=Pack(padding=10, width=120, background_color="#0d6efd", color="#ffffff"),
        )
        q_row.add(self.ask_btn)
        box.add(q_row)

        # Answer display
        box.add(toga.Label("Answer", style=Pack(padding=(10, 0, 5, 0), font_weight="bold")))
        self.answer_display = toga.MultilineTextInput(
            readonly=True,
            placeholder="Answer will appear here...",
            style=Pack(height=150, padding=(0, 0, 5, 0)),
        )
        box.add(self.answer_display)

        self.query_cost_label = toga.Label(
            "", style=Pack(padding=(0, 0, 5, 0), font_size=10, color="#666666")
        )
        box.add(self.query_cost_label)

        self.tab_content.add(box)

        # Populate listing selector if we have listings
        self._populate_query_listing_select()

        # B-15: restore any in-flight or completed query so that navigating
        # away from Knowledge mid-query and coming back still shows the
        # answer (or progress indicator) instead of a blank UI.
        self._restore_query_from_state()

    def _restore_query_from_state(self) -> None:
        """Pre-fill query UI from the persistent app-level state."""
        snap = self.app.query_states.knowledge.snapshot()
        status = snap.get("status", "idle")
        if status == "idle":
            return

        try:
            self.query_input.value = snap.get("query_text", "")
        except Exception:
            pass

        if status == "running":
            self._set_busy(True, "Query running in background...")
            try:
                self.ask_btn.enabled = False
            except Exception:
                pass
            try:
                self.query_cost_label.text = "Query running -- you may navigate away."
            except Exception:
                pass
            self.spawn_task(self._poll_marketplace_query_state(), name="poll_query")
        elif status == "done" and snap.get("result"):
            tx_msg = snap.get("extra", {}).get("tx_msg", "")
            self._apply_marketplace_query_result(snap["result"], tx_msg)
        elif status == "error":
            self._on_marketplace_error("Query", snap.get("error_msg") or "Unknown error")
            self._reenable_ask_btn()

    async def _poll_marketplace_query_state(self) -> None:
        """Poll app.query_states.knowledge until status leaves running."""
        import asyncio as _asyncio
        try:
            while not self._destroyed:
                await _asyncio.sleep(0.5)
                snap = self.app.query_states.knowledge.snapshot()
                if snap["status"] == "done" and snap.get("result"):
                    tx_msg = snap.get("extra", {}).get("tx_msg", "")
                    self._apply_marketplace_query_result(snap["result"], tx_msg)
                    return
                if snap["status"] == "error":
                    self._on_marketplace_error(
                        "Query", snap.get("error_msg") or "Unknown error"
                    )
                    self._reenable_ask_btn()
                    return
                if snap["status"] == "idle":
                    return
        except _asyncio.CancelledError:
            raise

    def _show_publish_tab(self, widget):
        """Show the Publish Knowledge tab."""
        try:
            self.tab_content.clear()
        except Exception:
            return
        # B-18: persist active tab.
        try:
            self.app.query_states.knowledge_browse.set_active_tab("publish")
        except Exception:
            pass
        box = toga.Box(style=Pack(direction=COLUMN))

        box.add(toga.Label("Publish Knowledge Collection", style=Pack(padding=(0, 0, 10, 0), font_weight="bold")))

        # Title
        box.add(toga.Label("Title", style=Pack(padding=(5, 0, 2, 0), font_size=11)))
        self.pub_title = toga.TextInput(
            placeholder="e.g. Machine Learning Fundamentals",
            style=Pack(padding=(0, 0, 5, 0)),
        )
        box.add(self.pub_title)

        # Description
        box.add(toga.Label("Description", style=Pack(padding=(5, 0, 2, 0), font_size=11)))
        self.pub_desc = toga.MultilineTextInput(
            placeholder="Describe what knowledge this collection contains...",
            style=Pack(height=60, padding=(0, 0, 5, 0)),
        )
        box.add(self.pub_desc)

        # Tags
        box.add(toga.Label("Tags (comma-separated)", style=Pack(padding=(5, 0, 2, 0), font_size=11)))
        self.pub_tags = toga.TextInput(
            placeholder="e.g. machine-learning, python, ai",
            style=Pack(padding=(0, 0, 5, 0)),
        )
        box.add(self.pub_tags)

        # Pricing row
        price_row = toga.Box(style=Pack(direction=ROW, padding=(5, 0)))
        price_row.add(toga.Label("Price/Query (BZT)", style=Pack(padding=(5, 10, 0, 0), font_size=11)))
        self.pub_price_query = toga.TextInput(
            value="1.0", style=Pack(width=80, padding_right=20)
        )
        price_row.add(self.pub_price_query)

        price_row.add(toga.Label("Purchase Price (BZT, 0=not for sale)", style=Pack(padding=(5, 10, 0, 0), font_size=11)))
        self.pub_price_purchase = toga.TextInput(
            value="0", style=Pack(width=80)
        )
        price_row.add(self.pub_price_purchase)
        box.add(price_row)

        # File selection
        box.add(toga.Label("Select Indexed Files", style=Pack(padding=(10, 0, 5, 0), font_weight="bold")))

        file_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 5, 0)))
        refresh_btn = toga.Button(
            "Refresh Files", on_press=self._on_refresh_publish_files,
            style=Pack(padding=5, width=110),
        )
        file_row.add(refresh_btn)
        self.pub_select_all_btn = toga.Button(
            "Select All", on_press=self._on_select_all_files,
            style=Pack(padding=5, width=90),
        )
        file_row.add(self.pub_select_all_btn)
        box.add(file_row)

        self.pub_file_table = toga.Table(
            headings=["Select", "File Name", "Chunks"],
            on_select=self._on_pub_file_select,
            style=Pack(height=120, padding=(5, 0)),
        )
        box.add(self.pub_file_table)
        self._pub_file_ids: list = []
        self._pub_selected_files: set = set()

        # Publish button
        pub_row = toga.Box(style=Pack(direction=ROW, padding=(10, 0)))
        pub_row.add(toga.Box(style=Pack(flex=1)))
        self.publish_btn = toga.Button(
            "Publish to Marketplace",
            on_press=self._on_publish,
            style=Pack(padding=10, width=200, background_color="#198754", color="#ffffff"),
        )
        pub_row.add(self.publish_btn)
        box.add(pub_row)

        self.tab_content.add(box)

        # Note: file list does NOT auto-refresh on tab switch. The user clicks
        # "Refresh Files" to load. This keeps tab switches snappy even when
        # the smart node is unreachable. Audit: D-04, D-05 freeze repro.

    def _show_my_listings_tab(self, widget):
        """Show My Listings management tab."""
        try:
            self.tab_content.clear()
        except Exception:
            return
        # B-18: persist active tab.
        try:
            self.app.query_states.knowledge_browse.set_active_tab("my_listings")
        except Exception:
            pass
        box = toga.Box(style=Pack(direction=COLUMN))

        header_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        header_row.add(toga.Label("My Knowledge Listings", style=Pack(font_weight="bold", flex=1)))
        refresh_btn = toga.Button(
            "Refresh", on_press=self._on_refresh_my_listings,
            style=Pack(padding=5, width=80),
        )
        header_row.add(refresh_btn)
        box.add(header_row)

        self.my_table = toga.Table(
            headings=["Title", "Status", "BZT/Query", "Buy Price", "Chunks", "Queries"],
            on_select=self._on_my_listing_select,
            style=Pack(height=180, padding=(5, 0)),
        )
        box.add(self.my_table)
        self._my_listing_ids: list = []
        self._my_selected_idx: int = -1

        # Action row
        action_row = toga.Box(style=Pack(direction=ROW, padding=(10, 0)))
        self.pause_btn = toga.Button(
            "Pause", on_press=self._on_pause_listing,
            style=Pack(padding=5, width=80), enabled=False,
        )
        action_row.add(self.pause_btn)
        self.unpublish_btn = toga.Button(
            "Unpublish", on_press=self._on_unpublish_listing,
            style=Pack(padding=5, width=100, background_color="#dc3545", color="#ffffff"),
            enabled=False,
        )
        action_row.add(self.unpublish_btn)
        box.add(action_row)

        self.tab_content.add(box)
        # Note: listings do NOT auto-refresh on tab switch (audit D-04/D-05).
        # The user clicks "Refresh" to load. Keeps tab switches snappy when
        # the smart node is unreachable.

    # === Node Management ===

    def _load_smart_nodes(self):
        """Load available smart nodes from consensus."""
        try:
            self.smart_nodes = list(getattr(self.app.state, "smart_nodes", []))
            if not self.smart_nodes:
                consensus = getattr(self.app.state, "consensus", {})
                nodes = consensus.get("nodes", [])
                self.smart_nodes = [
                    n for n in nodes
                    if isinstance(n, dict) and n.get("node_type") == "smart"
                    and not n.get("banned", False)
                ]

            if self.smart_nodes:
                items = []
                for n in self.smart_nodes:
                    nid = n.get("node_id", "?")
                    ip = n.get("ip", "?")
                    items.append(f"{nid[:16]}.. ({ip})")
                self.node_select.items = items
                self.selected_smart_node = self.smart_nodes[0]
            else:
                self.node_select.items = ["No smart nodes available"]
        except Exception as e:
            logger.error(f"[KNOWLEDGE] Error loading nodes: {e}")
            self.node_select.items = ["Error loading nodes"]

    def _on_node_selected(self, widget):
        """Handle smart node selection."""
        try:
            idx = self.node_select.items.index(widget.value)
            if idx < len(self.smart_nodes):
                self.selected_smart_node = self.smart_nodes[idx]
        except (ValueError, IndexError):
            pass

    def _get_smart_url(self) -> str:
        """Resolve the selected smart node to an HTTP URL.

        Production smart nodes always advertise a public IP via consensus, so
        we never want to fall back to localhost. If no smart node is selected,
        return None so callers can short-circuit and surface a friendly UI
        message instead of silently hitting a non-existent local server.
        """
        if not self.selected_smart_node:
            return ""
        from shared.client_core.docker_mapping import resolve_node_address
        ip = self.selected_smart_node.get("ip", "")
        if not ip:
            return ""
        try:
            host_ip, port = resolve_node_address(ip, use_zmq=False)
        except Exception:
            host_ip, port = ip, 5000
        return f"http://{host_ip}:{port}"

    # === Browse Handlers ===

    def _on_search(self, widget):
        """Search the marketplace."""
        if self._busy:
            return
        if not self.selected_smart_node:
            self.status_label.text = "Select a smart node first."
            return

        # Capture UI values on the main thread BEFORE spawning the worker.
        query_text = ""
        tags = None
        try:
            si = getattr(self, "search_input", None)
            query_text = si.value.strip() if si and si.value else ""
            ti = getattr(self, "tag_input", None)
            tags = [t.strip() for t in ti.value.split(",") if t.strip()] if ti and ti.value else None
        except Exception:
            pass

        smart_url = self._get_smart_url()
        self._set_busy(True, "Searching marketplace...")

        def do_search():
            try:
                from shared.client_core.knowledge_client import KnowledgeMarketplaceClient
                client = KnowledgeMarketplaceClient(smart_url, timeout=_MARKETPLACE_TIMEOUT_S)
                results = client.search_marketplace(query=query_text, tags=tags)
                self.safe_ui_call(self._apply_search_results, results)
            except Exception as e:
                err = str(e)
                self.safe_ui_call(self._on_marketplace_error, "Search", err)

        self.spawn_worker(do_search, name="search_marketplace")

    def _apply_search_results(self, results):
        """Render search results - main thread only via safe_ui_call."""
        self._set_busy(False)
        self.listings = list(results)

        # B-18: persist on the app so we can re-hydrate this exact list
        # after the view is destroyed and rebuilt.
        try:
            search_query = ""
            search_tags = ""
            si = getattr(self, "search_input", None)
            if si is not None and si.value:
                search_query = si.value
            ti = getattr(self, "tag_input", None)
            if ti is not None and ti.value:
                search_tags = ti.value
            self.app.query_states.knowledge_browse.set_listings(
                self.listings,
                search_query=search_query,
                search_tags=search_tags,
            )
        except Exception as exc:
            logger.debug(f"[KNOWLEDGE] persist listings failed: {exc}")

        self._render_browse_table_from_listings()
        self.status_label.text = f"Found {len(results)} listings"
        self._clear_reachability_warning()

    def _render_browse_table_from_listings(self) -> None:
        """Push self.listings into the Browse table widget.

        Pulled out so the persisted snapshot can be replayed on view
        rebuild (B-18) without going through the network again.
        """
        if not getattr(self, "browse_table", None):
            return
        data = []
        self._browse_listing_ids = []
        for r in self.listings:
            data.append((
                r.get("title", "Untitled"),
                (r.get("seller_address", "")[:12] + "...") if r.get("seller_address") else "?",
                str(r.get("price_per_query", "?")),
                str(r.get("purchase_price", 0)) if r.get("purchase_price", 0) > 0 else "--",
                str(r.get("total_chunks", 0)),
                str(r.get("total_queries", 0)),
            ))
            self._browse_listing_ids.append(r.get("listing_id", ""))
        try:
            self.browse_table.data = data
        except Exception:
            pass

    def _on_browse_select(self, widget):
        """Handle browse table row selection."""
        try:
            selection = widget.selection
            if selection is None:
                self._selected_listing_idx = -1
                self.query_listing_btn.enabled = False
                self.buy_listing_btn.enabled = False
                return

            # Try direct identity match first, then index-based fallback
            matched_idx = -1
            for idx, row in enumerate(self.browse_table.data):
                if row is selection or row == selection:
                    matched_idx = idx
                    break

            # Fallback: use Toga's selection index if available
            if matched_idx < 0:
                try:
                    data_list = list(self.browse_table.data)
                    matched_idx = data_list.index(selection)
                except (ValueError, TypeError):
                    pass

            if matched_idx < 0 or matched_idx >= len(self.listings):
                logger.warning(f"[KNOWLEDGE] Browse select: no match (selection={selection})")
                return

            self._selected_listing_idx = matched_idx
            listing = self.listings[matched_idx]
            self.selected_listing = listing
            # B-18: persist the selection so view rebuild restores it.
            try:
                self.app.query_states.knowledge_browse.set_selected(listing)
            except Exception:
                pass
            self.query_listing_btn.enabled = True

            desc = listing.get("description", "")[:120]
            tags = ", ".join(listing.get("tags", []))
            self.listing_detail_label.text = (
                f"{desc}{'...' if len(listing.get('description', '')) > 120 else ''}"
                f" | Tags: {tags or 'none'}"
            )

            pp = float(listing.get("purchase_price", 0))
            # Prevent self-purchase: disable button if seller is the current wallet
            is_own = False
            try:
                wallet = self.app.client.get_current_wallet()
                if wallet and listing.get("seller_address") == wallet.address:
                    is_own = True
            except Exception:
                pass
            self.buy_listing_btn.enabled = pp > 0 and not is_own
            logger.info(f"[KNOWLEDGE] Selected listing idx={matched_idx} "
                       f"title={listing.get('title', '?')!r} purchase_price={pp} "
                       f"own={is_own}")

        except Exception as e:
            logger.error(f"[KNOWLEDGE] Browse select error: {e}")
            import traceback; traceback.print_exc()

    def _on_query_listing_from_browse(self, widget):
        """Switch to query tab with selected listing."""
        if self._selected_listing_idx >= 0 and self._selected_listing_idx < len(self.listings):
            self.selected_listing = self.listings[self._selected_listing_idx]
            self._show_query_tab(None)
            self._populate_query_listing_select()

    # === Query Handlers ===

    def _populate_query_listing_select(self):
        """Populate the query listing selector from cached listings."""
        if not self.listings:
            return
        try:
            items = []
            for ls in self.listings:
                title = ls.get("title", "Untitled")
                ppq = ls.get("price_per_query", "?")
                items.append(f"{title[:30]} ({ppq} BZT/query)")
            self.query_listing_select.items = items
            # Select the browsed listing if set
            if self.selected_listing:
                lid = self.selected_listing.get("listing_id")
                for i, ls in enumerate(self.listings):
                    if ls.get("listing_id") == lid:
                        self.query_listing_select.value = items[i]
                        self._on_query_listing_changed(self.query_listing_select)
                        break
        except Exception:
            pass

    def _on_query_listing_changed(self, widget):
        """Handle query listing selection change."""
        try:
            idx = self.query_listing_select.items.index(widget.value)
            if idx < len(self.listings):
                self.selected_listing = self.listings[idx]
                ls = self.selected_listing
                self.query_listing_info.text = (
                    f"Seller: {ls.get('seller_address', '?')[:16]}... | "
                    f"Chunks: {ls.get('total_chunks', 0)} | "
                    f"Cost: {ls.get('price_per_query', '?')} BZT/query"
                )
        except (ValueError, IndexError):
            pass

    def _on_marketplace_query(self, widget):
        """Handle marketplace query button."""
        if self._busy:
            return
        query_text = self.query_input.value
        if not query_text or not query_text.strip():
            self.query_cost_label.text = "Please enter a question."
            return
        if not self.selected_listing:
            self.query_cost_label.text = "Select a listing to query."
            return
        if not self.selected_smart_node:
            self.query_cost_label.text = "Select a smart node."
            return

        self.ask_btn.enabled = False
        self.answer_display.value = ""
        self._set_busy(True, "Loading embedding model & querying...")

        # Capture all UI / state values on the main thread before spawning
        q_text = query_text.strip()
        smart_url = self._get_smart_url()
        listing = dict(self.selected_listing)
        wallet = self.app.client.get_current_wallet()
        smart_node_id = self.selected_smart_node.get("node_id", "")
        smart_node_wallet = self.selected_smart_node.get("wallet_address", "")

        # Snapshot wallet credentials so the worker never touches `wallet` later
        wallet_addr = wallet.address
        wallet_privkey = wallet.privkey.hex()
        wallet_pubkey = wallet.get_pubkey_hex()

        # B-15: persist the in-flight query so a re-built view can find it.
        qstate = self.app.query_states.knowledge
        qstate.begin(
            query_text=q_text,
            extra={
                "listing_id": listing.get("listing_id", ""),
                "listing_title": listing.get("title", ""),
                "smart_node_id": smart_node_id,
                "smart_node_label": self.selected_smart_node.get("ip", "this smart node"),
            },
        )

        def do_query():
            try:
                from shared.client_core.knowledge_client import (
                    KnowledgeMarketplaceClient, build_knowledge_query_tx,
                )

                # Marketplace query is a long-running RAG round-trip; allow the
                # client default timeout (30s) instead of the metadata one.
                client = KnowledgeMarketplaceClient(smart_url)

                model = _get_embed_model()
                embeddings = list(model.embed([q_text]))
                query_vector = embeddings[0].tolist()

                result = client.query_listing(
                    listing_id=listing["listing_id"],
                    query_text=q_text,
                    query_vector=query_vector,
                    buyer_address=wallet_addr,
                    top_k=5,
                )

                tx_msg = ""
                try:
                    tx = build_knowledge_query_tx(
                        buyer_address=wallet_addr,
                        seller_address=listing.get("seller_address", ""),
                        listing_id=listing["listing_id"],
                        query_hash=result.get("query_hash", ""),
                        answer_hash=result.get("answer_hash", ""),
                        cost=float(result.get("cost", 0)),
                        smart_node_id=smart_node_id,
                        smart_node_wallet=smart_node_wallet,
                        private_key_hex=wallet_privkey,
                        public_key_hex=wallet_pubkey,
                    )
                    resp, status = self.app.client.send_raw_transaction(tx)
                    if status == 200:
                        tx_msg = f" | TX: {tx['tx_hash'][:12]}..."
                    else:
                        tx_msg = " | TX failed"
                except Exception as tx_err:
                    logger.error(f"[KNOWLEDGE] TX error: {tx_err}")

                # Persist BEFORE notifying the (possibly dead) view.
                # Stash tx_msg in extra so a fresh view rebuild can show it.
                snap_extra = qstate.snapshot().get("extra", {})
                snap_extra["tx_msg"] = tx_msg
                qstate.extra = snap_extra
                qstate.succeed(result)
                self.safe_ui_call(self._apply_marketplace_query_result, result, tx_msg)

            except Exception as e:
                error_msg = str(e)
                qstate.fail(error_msg)
                self.safe_ui_call(self._on_marketplace_error, "Query", error_msg)
                self.safe_ui_call(self._reenable_ask_btn)

        self.spawn_worker(do_query, name="marketplace_query")

    def _apply_marketplace_query_result(self, result, tx_msg: str) -> None:
        self._set_busy(False)
        self.ask_btn.enabled = True
        self.answer_display.value = result.get("answer", "No answer.")
        cost = result.get("cost", 0)
        self.query_cost_label.text = f"Cost: {cost} BZT{tx_msg}"
        self._clear_reachability_warning()

    def _reenable_ask_btn(self) -> None:
        try:
            self.ask_btn.enabled = True
        except Exception:
            pass

    # === Purchase Handler ===

    def _on_purchase_listing(self, widget):
        """Handle purchase button click."""
        if self._busy:
            return
        if self._selected_listing_idx < 0 or self._selected_listing_idx >= len(self.listings):
            self.status_label.text = "Select a listing first."
            return

        listing = self.listings[self._selected_listing_idx]
        if listing.get("purchase_price", 0) <= 0:
            self.status_label.text = "This listing is not for sale."
            return

        # Prevent self-purchase
        try:
            wallet = self.app.client.get_current_wallet()
            if wallet and listing.get("seller_address") == wallet.address:
                self.status_label.text = "Cannot purchase your own listing."
                return
        except Exception:
            pass

        self.buy_listing_btn.enabled = False
        self._set_busy(True, f"Purchasing {listing.get('title', 'listing')}...")

        smart_url = self._get_smart_url()
        wallet = self.app.client.get_current_wallet()
        wallet_address = wallet.address
        privkey_hex = wallet.privkey.hex()
        pubkey_hex = wallet.get_pubkey_hex()
        listing_id = listing["listing_id"]

        def do_purchase():
            try:
                from shared.client_core.knowledge_client import (
                    KnowledgeMarketplaceClient, build_knowledge_purchase_tx,
                )

                client = KnowledgeMarketplaceClient(smart_url, timeout=_MARKETPLACE_TIMEOUT_S)

                full_listing = client.get_listing(listing_id)
                file_ids = full_listing.get("file_ids", [])
                if not file_ids:
                    raise ValueError("Listing has no file_ids -- cannot build purchase TX")

                result = client.purchase_listing(
                    listing_id=listing_id,
                    buyer_address=wallet_address,
                )

                tx_msg = ""
                try:
                    tx = build_knowledge_purchase_tx(
                        buyer_address=wallet_address,
                        seller_address=full_listing.get("seller_address", ""),
                        listing_id=listing_id,
                        purchase_price=float(full_listing.get("purchase_price", 0)),
                        file_ids=file_ids,
                        private_key_hex=privkey_hex,
                        public_key_hex=pubkey_hex,
                    )
                    resp, status = self.app.client.send_raw_transaction(tx)
                    if status == 200:
                        tx_msg = f" | TX: {tx['tx_hash'][:12]}..."
                except Exception as tx_err:
                    logger.error(f"[KNOWLEDGE] Purchase TX error: {tx_err}")

                msg = f"Purchased! Price: {full_listing.get('purchase_price', 0)} BZT{tx_msg}"
                self.safe_ui_call(self._after_purchase, msg, True)
            except Exception as e:
                err_msg = str(e)
                self.safe_ui_call(self._after_purchase, f"Purchase error: {err_msg}", False)

        self.spawn_worker(do_purchase, name="purchase_listing")

    def _after_purchase(self, msg: str, success: bool) -> None:
        self._set_busy(False)
        self.buy_listing_btn.enabled = True
        self.status_label.text = msg
        if success:
            self._clear_reachability_warning()

    # === Publish Handlers ===

    def _on_refresh_publish_files(self, widget):
        """Refresh the list of indexed files for publishing."""
        if self._busy:
            return
        if not self.selected_smart_node:
            return

        smart_url = self._get_smart_url()
        wallet = self.app.client.get_current_wallet()
        wallet_address = wallet.address if wallet else None
        self._set_busy(True, "Loading indexed files...")

        def do_refresh():
            try:
                if not wallet_address:
                    raise ValueError("No wallet connected")
                from shared.client_core.smart_client import SmartNodeClient
                client = SmartNodeClient(smart_url, timeout=_MARKETPLACE_TIMEOUT_S)
                stats = client.get_workspace_stats(wallet_address)
                files = stats.get("files", [])
                self.safe_ui_call(self._apply_publish_files, files)
            except Exception as e:
                err_msg = str(e)
                self.safe_ui_call(self._on_marketplace_error, "Loading files", err_msg)

        self.spawn_worker(do_refresh, name="refresh_publish_files")

    def _apply_publish_files(self, files) -> None:
        self._set_busy(False)
        data = []
        self._pub_file_ids = []
        self._pub_selected_files = set()
        for f in files:
            fid = f.get("file_id", "")
            data.append((
                "[ ]",
                f.get("file_name", "unknown"),
                str(f.get("num_chunks", 0)),
            ))
            self._pub_file_ids.append(fid)
        try:
            self.pub_file_table.data = data
        except Exception:
            pass
        self._clear_reachability_warning()

    def _on_pub_file_select(self, widget):
        """Toggle file selection for publishing."""
        try:
            if widget.selection is not None:
                for idx, row in enumerate(self.pub_file_table.data):
                    if row == widget.selection:
                        fid = self._pub_file_ids[idx]
                        if fid in self._pub_selected_files:
                            self._pub_selected_files.discard(fid)
                            new_data = list(self.pub_file_table.data)
                            new_data[idx] = ("[ ]", row[1], row[2])
                        else:
                            self._pub_selected_files.add(fid)
                            new_data = list(self.pub_file_table.data)
                            new_data[idx] = ("[x]", row[1], row[2])
                        self.pub_file_table.data = new_data
                        break
        except Exception:
            pass

    def _on_select_all_files(self, widget):
        """Select/deselect all files."""
        if len(self._pub_selected_files) == len(self._pub_file_ids):
            # Deselect all
            self._pub_selected_files.clear()
            new_data = [("[ ]", row[1], row[2]) for row in self.pub_file_table.data]
        else:
            # Select all
            self._pub_selected_files = set(self._pub_file_ids)
            new_data = [("[x]", row[1], row[2]) for row in self.pub_file_table.data]
        self.pub_file_table.data = new_data

    def _on_publish(self, widget):
        """Handle publish button."""
        if self._busy:
            return
        title = self.pub_title.value.strip() if self.pub_title.value else ""
        if not title:
            self.status_label.text = "Title is required."
            return
        if not self._pub_selected_files:
            self.status_label.text = "Select at least one file."
            return
        if not self.selected_smart_node:
            self.status_label.text = "Select a smart node."
            return

        self.publish_btn.enabled = False
        self._set_busy(True, "Publishing knowledge listing...")

        description = self.pub_desc.value.strip() if self.pub_desc.value else ""
        tags = [t.strip() for t in (self.pub_tags.value or "").split(",") if t.strip()]
        try:
            ppq = float(self.pub_price_query.value or "1.0")
        except ValueError:
            ppq = 1.0
        try:
            pp = float(self.pub_price_purchase.value or "0")
        except ValueError:
            pp = 0

        file_ids = list(self._pub_selected_files)

        wallet = self.app.client.get_current_wallet()
        marketplace_key = derive_encryption_key(wallet)
        smart_url = self._get_smart_url()
        smart_node_id = self.selected_smart_node.get("node_id", "")
        wallet_address = wallet.address
        privkey_hex = wallet.privkey.hex()
        pubkey_hex = wallet.get_pubkey_hex()

        def do_publish():
            try:
                from shared.client_core.knowledge_client import (
                    KnowledgeMarketplaceClient, build_knowledge_publish_tx,
                )

                # Publish involves uploading chunks - allow longer timeout
                client = KnowledgeMarketplaceClient(smart_url, timeout=60)

                result = client.publish_listing(
                    seller_address=wallet_address,
                    title=title,
                    description=description,
                    tags=tags,
                    price_per_query=ppq,
                    purchase_price=pp,
                    file_ids=file_ids,
                    marketplace_key=marketplace_key,
                )

                listing_id = result.get("listing_id", "")
                total_files = result.get("total_files", 0)
                total_chunks = result.get("total_chunks", 0)

                tx_msg = ""
                try:
                    tx = build_knowledge_publish_tx(
                        seller_address=wallet_address,
                        listing_id=listing_id,
                        smart_node_id=smart_node_id,
                        title=title,
                        file_count=total_files,
                        chunk_count=total_chunks,
                        price_per_query=ppq,
                        purchase_price=pp,
                        private_key_hex=privkey_hex,
                        public_key_hex=pubkey_hex,
                    )
                    resp, status = self.app.client.send_raw_transaction(tx)
                    if status == 200:
                        tx_msg = f" | TX: {tx['tx_hash'][:12]}..."
                except Exception as tx_err:
                    logger.error(f"[KNOWLEDGE] Publish TX error: {tx_err}")

                msg = (f"Published! {total_files} files, {total_chunks} chunks, "
                       f"ID: {listing_id[:12]}...{tx_msg}")

                self.safe_ui_call(self._after_publish, msg, True)

            except Exception as e:
                error_msg = str(e)
                self.safe_ui_call(self._after_publish, f"Publish error: {error_msg}", False)

        self.spawn_worker(do_publish, name="publish_listing")

    def _after_publish(self, msg: str, success: bool) -> None:
        self._set_busy(False)
        try:
            self.publish_btn.enabled = True
        except Exception:
            pass
        self.status_label.text = msg
        if success:
            self._clear_reachability_warning()

    # === My Listings Handlers ===

    def _on_refresh_my_listings(self, widget):
        """Refresh the user's own listings."""
        if self._busy:
            return
        if not self.selected_smart_node:
            return

        smart_url = self._get_smart_url()
        wallet = self.app.client.get_current_wallet()
        wallet_address = wallet.address if wallet else None
        self._set_busy(True, "Loading your listings...")

        def do_refresh():
            try:
                if not wallet_address:
                    raise ValueError("No wallet connected")
                from shared.client_core.knowledge_client import KnowledgeMarketplaceClient
                client = KnowledgeMarketplaceClient(smart_url, timeout=_MARKETPLACE_TIMEOUT_S)
                results = client.get_my_listings(wallet_address)
                self.safe_ui_call(self._apply_my_listings, results)
            except Exception as e:
                err_msg = str(e)
                self.safe_ui_call(self._on_marketplace_error, "My listings", err_msg)

        self.spawn_worker(do_refresh, name="refresh_my_listings")

    def _apply_my_listings(self, results) -> None:
        self._set_busy(False)
        self.my_listings = list(results)
        data = []
        self._my_listing_ids = []
        for r in results:
            data.append((
                r.get("title", "Untitled"),
                r.get("status", "?"),
                str(r.get("price_per_query", "?")),
                str(r.get("purchase_price", 0)) if r.get("purchase_price", 0) > 0 else "--",
                str(r.get("total_chunks", 0)),
                str(r.get("total_queries", 0)),
            ))
            self._my_listing_ids.append(r.get("listing_id", ""))
        try:
            self.my_table.data = data
        except Exception:
            pass
        self.status_label.text = f"{len(results)} listings"
        self._clear_reachability_warning()

    def _on_my_listing_select(self, widget):
        """Handle my listing table selection."""
        try:
            if widget.selection is not None:
                for idx, row in enumerate(self.my_table.data):
                    if row == widget.selection:
                        self._my_selected_idx = idx
                        self.pause_btn.enabled = True
                        self.unpublish_btn.enabled = True
                        return
            self._my_selected_idx = -1
            self.pause_btn.enabled = False
            self.unpublish_btn.enabled = False
        except Exception:
            pass

    def _on_pause_listing(self, widget):
        """Toggle pause/resume on selected listing."""
        if self._busy:
            return
        if self._my_selected_idx < 0 or self._my_selected_idx >= len(self.my_listings):
            return

        listing = self.my_listings[self._my_selected_idx]
        new_status = "paused" if listing.get("status") == "active" else "active"

        smart_url = self._get_smart_url()
        wallet = self.app.client.get_current_wallet()
        wallet_address = wallet.address if wallet else ""
        lid = listing["listing_id"]
        self._set_busy(True, f"{'Pausing' if new_status == 'paused' else 'Resuming'} listing...")

        def do_update():
            try:
                from shared.client_core.knowledge_client import KnowledgeMarketplaceClient
                client = KnowledgeMarketplaceClient(smart_url, timeout=_MARKETPLACE_TIMEOUT_S)
                client.update_listing(lid, wallet_address, status=new_status)
                self.safe_ui_call(self._after_listing_action, f"Listing {new_status}", True)
            except Exception as e:
                err_msg = str(e)
                self.safe_ui_call(self._after_listing_action, f"Error: {err_msg}", False)

        self.spawn_worker(do_update, name="pause_listing")

    def _on_unpublish_listing(self, widget):
        """Delete/unpublish selected listing."""
        if self._busy:
            return
        if self._my_selected_idx < 0 or self._my_selected_idx >= len(self.my_listings):
            return

        listing = self.my_listings[self._my_selected_idx]

        smart_url = self._get_smart_url()
        wallet = self.app.client.get_current_wallet()
        wallet_address = wallet.address if wallet else ""
        lid = listing["listing_id"]
        self._set_busy(True, "Unpublishing listing...")

        def do_delete():
            try:
                from shared.client_core.knowledge_client import KnowledgeMarketplaceClient
                client = KnowledgeMarketplaceClient(smart_url, timeout=_MARKETPLACE_TIMEOUT_S)
                client.delete_listing(lid, wallet_address)
                self.safe_ui_call(self._after_listing_action, "Listing unpublished.", True)
            except Exception as e:
                err_msg = str(e)
                self.safe_ui_call(self._after_listing_action, f"Error: {err_msg}", False)

        self.spawn_worker(do_delete, name="unpublish_listing")

    def _after_listing_action(self, msg: str, success: bool) -> None:
        self._set_busy(False)
        self.status_label.text = msg
        if success:
            self._clear_reachability_warning()
            self._on_refresh_my_listings(None)

    # ------------------------------------------------------------------
    # Reachability banner + connection-error handler
    # ------------------------------------------------------------------

    def _on_marketplace_error(self, op: str, err: str) -> None:
        """Surface marketplace worker errors. Distinguishes between:

        - real reachability problems (node down, connection refused, timeout)
          -> "Smart node unreachable" banner
        - listing-not-found-on-this-node (a different smart node has the
          listing because marketplace data isn't replicated yet)
          -> "Listing not on this node" banner
        - everything else -> generic status line.

        This was the B-15 confusion: any error from the picked smart node
        was labelled "unreachable" even when the node was healthy and the
        real issue was that the listing lived on a sibling node.
        """
        self._set_busy(False)
        try:
            self.status_label.text = f"{op} error: {err}"
        except Exception:
            pass

        from beezdesktop.query_state import classify_smart_node_error
        kind = classify_smart_node_error(err)
        smart_label = (self.selected_smart_node or {}).get("ip", "this smart node")
        if kind == "unreachable":
            self._show_reachability_warning(
                f"[!] {smart_label} is unreachable. Pick another smart node above."
            )
        elif kind == "not_found":
            self._show_reachability_warning(
                f"[!] This listing isn't available on {smart_label}. "
                "Marketplace data may not be replicated yet -- pick another "
                "smart node above and retry."
            )
        elif kind in ("auth", "server"):
            self._show_reachability_warning(
                f"[!] {smart_label} returned an error ({kind}). "
                "Try another smart node or contact support."
            )

    def _show_reachability_warning(self, message: str | None = None) -> None:
        if self._reachability_label is None:
            return
        try:
            self._reachability_label.text = message or (
                "[!] Smart node unreachable. Check the node status or pick "
                "another smart node above."
            )
            self._has_warned_unreachable = True
        except Exception:
            pass

    def _clear_reachability_warning(self) -> None:
        if not self._has_warned_unreachable or self._reachability_label is None:
            return
        try:
            self._reachability_label.text = ""
            self._has_warned_unreachable = False
        except Exception:
            pass

    def _kick_off_fastembed_warmup(self) -> None:
        """Pre-warm the fastembed model on a daemon thread.

        First-time download is ~33 MB and can take several seconds; doing
        it in the background means the first marketplace query feels much
        snappier and the lock contention is gone after warm-up completes.
        """
        if _embed_model is not None:
            return
        self.spawn_worker(prewarm_embed_model, name="fastembed_warmup")
