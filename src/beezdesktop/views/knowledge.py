"""
Knowledge Marketplace View

Provides a UI for the knowledge marketplace:
- Browse/search published knowledge collections
- Query a listing (pay-per-query, answers only)
- Publish your own indexed files as a knowledge listing
- Manage your listings (edit, pause, unpublish)
- Purchase full ownership of a listing
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import threading
import hashlib


class KnowledgeView:
    """Knowledge marketplace interface."""

    def __init__(self, app):
        self.app = app
        self.selected_smart_node = None
        self.smart_nodes = []
        self.listings = []
        self.my_listings = []
        self.selected_listing = None
        self._selected_listing_idx = -1

    def build(self) -> toga.Box:
        """Build the knowledge marketplace view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        # Header
        header = toga.Label(
            "Knowledge Marketplace",
            style=Pack(padding=(0, 0, 5, 0), font_size=24, font_weight="bold"),
        )
        container.add(header)

        subtitle = toga.Label(
            "Buy, sell, and query knowledge collections powered by RAG",
            style=Pack(padding=(0, 0, 15, 0), font_size=12, color="#666666"),
        )
        container.add(subtitle)

        # Wallet check
        if not self.app.client or not self.app.client.is_wallet_connected():
            container.add(
                toga.Label(
                    "Please connect a wallet first.",
                    style=Pack(padding=20, font_size=14, color="#cc0000"),
                )
            )
            return container

        # Smart node selector
        container.add(self._build_node_selector())

        # Tab row for Browse / Query / Publish / My Listings
        container.add(self._build_tab_bar())

        # Content area (changes based on tab)
        self.tab_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
        container.add(self.tab_content)

        # Status bar
        self.status_label = toga.Label(
            "",
            style=Pack(padding=(5, 0), font_size=10, color="#666666"),
        )
        container.add(self.status_label)

        # Load smart nodes and show browse tab
        self._load_smart_nodes()
        self._show_browse_tab(None)

        return container

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
        bar = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
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
                style=Pack(padding=5, width=110),
            )
            bar.add(btn)
        return bar

    # === Tab Content Builders ===

    def _show_browse_tab(self, widget):
        """Show the Browse Marketplace tab."""
        self.tab_content.clear()
        box = toga.Box(style=Pack(direction=COLUMN))

        # Search row
        search_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        self.search_input = toga.TextInput(
            placeholder="Search knowledge collections...",
            style=Pack(flex=1, padding_right=10),
        )
        search_row.add(self.search_input)

        self.tag_input = toga.TextInput(
            placeholder="Tags (comma-separated)",
            style=Pack(width=180, padding_right=10),
        )
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

        # Auto-search
        self._on_search(None)

    def _show_query_tab(self, widget):
        """Show the Query a Listing tab."""
        self.tab_content.clear()
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

    def _show_publish_tab(self, widget):
        """Show the Publish Knowledge tab."""
        self.tab_content.clear()
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

        # Load files
        self._on_refresh_publish_files(None)

    def _show_my_listings_tab(self, widget):
        """Show My Listings management tab."""
        self.tab_content.clear()
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
        self._on_refresh_my_listings(None)

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
            print(f"[KNOWLEDGE] Error loading nodes: {e}", flush=True)
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
        """Resolve the selected smart node to an HTTP URL."""
        from shared.client_core.docker_mapping import resolve_node_address
        ip = self.selected_smart_node.get("ip", "smart1")
        host_ip, port = resolve_node_address(ip, use_zmq=False)
        return f"http://{host_ip}:{port}"

    # === Browse Handlers ===

    def _on_search(self, widget):
        """Search the marketplace."""
        if not self.selected_smart_node:
            self.status_label.text = "Select a smart node first."
            return

        self.status_label.text = "Searching..."

        def do_search():
            try:
                from shared.client_core.knowledge_client import KnowledgeMarketplaceClient
                client = KnowledgeMarketplaceClient(self._get_smart_url())

                query = getattr(self, "search_input", None)
                query_text = query.value.strip() if query and query.value else ""
                tag_text = getattr(self, "tag_input", None)
                tags = [t.strip() for t in tag_text.value.split(",") if t.strip()] if tag_text and tag_text.value else None

                results = client.search_marketplace(query=query_text, tags=tags)
                self.listings = results

                def update_ui():
                    data = []
                    self._browse_listing_ids = []
                    for r in results:
                        data.append((
                            r.get("title", "Untitled"),
                            (r.get("seller_address", "")[:12] + "...") if r.get("seller_address") else "?",
                            str(r.get("price_per_query", "?")),
                            str(r.get("purchase_price", 0)) if r.get("purchase_price", 0) > 0 else "--",
                            str(r.get("total_chunks", 0)),
                            str(r.get("total_queries", 0)),
                        ))
                        self._browse_listing_ids.append(r.get("listing_id", ""))
                    self.browse_table.data = data
                    self.status_label.text = f"Found {len(results)} listings"

                self.app.loop.call_soon_threadsafe(update_ui)
            except Exception as e:
                self.app.loop.call_soon_threadsafe(
                    setattr, self.status_label, "text", f"Search error: {e}"
                )

        threading.Thread(target=do_search, daemon=True).start()

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
                print(f"[KNOWLEDGE] Browse select: no match (selection={selection})", flush=True)
                return

            self._selected_listing_idx = matched_idx
            listing = self.listings[matched_idx]
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
            print(f"[KNOWLEDGE] Selected listing idx={matched_idx} "
                  f"title={listing.get('title', '?')!r} purchase_price={pp} "
                  f"own={is_own}", flush=True)

        except Exception as e:
            print(f"[KNOWLEDGE] Browse select error: {e}", flush=True)
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
        self.query_cost_label.text = "Processing query..."
        self.answer_display.value = ""

        def do_query():
            try:
                from shared.client_core.knowledge_client import (
                    KnowledgeMarketplaceClient, build_knowledge_query_tx,
                )
                from shared.client_core.docker_mapping import resolve_node_address

                smart_url = self._get_smart_url()
                client = KnowledgeMarketplaceClient(smart_url)
                wallet = self.app.client.get_current_wallet()
                listing = self.selected_listing

                # Generate query embedding
                from fastembed import TextEmbedding
                model = TextEmbedding("BAAI/bge-small-en-v1.5")
                embeddings = list(model.embed([query_text.strip()]))
                query_vector = embeddings[0].tolist()

                result = client.query_listing(
                    listing_id=listing["listing_id"],
                    query_text=query_text.strip(),
                    query_vector=query_vector,
                    buyer_address=wallet.address,
                    top_k=5,
                )

                # Build and broadcast knowledge_query TX
                tx_msg = ""
                try:
                    smart_node_id = self.selected_smart_node.get("node_id", "")
                    smart_node_wallet = self.selected_smart_node.get("wallet_address", "")
                    tx = build_knowledge_query_tx(
                        buyer_address=wallet.address,
                        seller_address=listing.get("seller_address", ""),
                        listing_id=listing["listing_id"],
                        query_hash=result.get("query_hash", ""),
                        answer_hash=result.get("answer_hash", ""),
                        cost=float(result.get("cost", 0)),
                        smart_node_id=smart_node_id,
                        smart_node_wallet=smart_node_wallet,
                        private_key_hex=wallet.privkey.hex(),
                        public_key_hex=wallet.get_pubkey_hex(),
                    )
                    resp, status = self.app.client.send_raw_transaction(tx)
                    if status == 200:
                        tx_msg = f" | TX: {tx['tx_hash'][:12]}..."
                    else:
                        tx_msg = f" | TX failed"
                except Exception as tx_err:
                    print(f"[KNOWLEDGE] TX error: {tx_err}", flush=True)

                def update_ui():
                    self.ask_btn.enabled = True
                    self.answer_display.value = result.get("answer", "No answer.")
                    cost = result.get("cost", 0)
                    self.query_cost_label.text = f"Cost: {cost} BZT{tx_msg}"

                self.app.loop.call_soon_threadsafe(update_ui)

            except Exception as e:
                error_msg = str(e)
                def show_err():
                    self.ask_btn.enabled = True
                    self.query_cost_label.text = f"Error: {error_msg}"
                self.app.loop.call_soon_threadsafe(show_err)

        threading.Thread(target=do_query, daemon=True).start()

    # === Purchase Handler ===

    def _on_purchase_listing(self, widget):
        """Handle purchase button click."""
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

        self.status_label.text = f"Purchasing {listing.get('title', 'listing')}..."
        self.buy_listing_btn.enabled = False

        def do_purchase():
            try:
                from shared.client_core.knowledge_client import (
                    KnowledgeMarketplaceClient, build_knowledge_purchase_tx,
                )

                smart_url = self._get_smart_url()
                client = KnowledgeMarketplaceClient(smart_url)
                wallet = self.app.client.get_current_wallet()

                # Fetch full listing details (search results don't include file_ids)
                full_listing = client.get_listing(listing["listing_id"])
                file_ids = full_listing.get("file_ids", [])
                if not file_ids:
                    raise ValueError("Listing has no file_ids -- cannot build purchase TX")

                result = client.purchase_listing(
                    listing_id=listing["listing_id"],
                    buyer_address=wallet.address,
                )

                # Build and broadcast knowledge_purchase TX
                tx_msg = ""
                try:
                    tx = build_knowledge_purchase_tx(
                        buyer_address=wallet.address,
                        seller_address=full_listing.get("seller_address", ""),
                        listing_id=listing["listing_id"],
                        purchase_price=float(full_listing.get("purchase_price", 0)),
                        file_ids=file_ids,
                        private_key_hex=wallet.privkey.hex(),
                        public_key_hex=wallet.get_pubkey_hex(),
                    )
                    resp, status = self.app.client.send_raw_transaction(tx)
                    if status == 200:
                        tx_msg = f" | TX: {tx['tx_hash'][:12]}..."
                except Exception as tx_err:
                    print(f"[KNOWLEDGE] Purchase TX error: {tx_err}", flush=True)

                msg = f"Purchased! Price: {full_listing.get('purchase_price', 0)} BZT{tx_msg}"
                self.app.loop.call_soon_threadsafe(
                    setattr, self.status_label, "text", msg
                )
            except Exception as e:
                self.app.loop.call_soon_threadsafe(
                    setattr, self.status_label, "text", f"Purchase error: {e}"
                )
            finally:
                # Re-enable the purchase button so user can retry on error
                self.app.loop.call_soon_threadsafe(
                    setattr, self.buy_listing_btn, "enabled", True
                )

        threading.Thread(target=do_purchase, daemon=True).start()

    # === Publish Handlers ===

    def _on_refresh_publish_files(self, widget):
        """Refresh the list of indexed files for publishing."""
        if not self.selected_smart_node:
            return

        def do_refresh():
            try:
                from shared.client_core.smart_client import SmartNodeClient
                smart_url = self._get_smart_url()
                client = SmartNodeClient(smart_url, timeout=10)
                wallet = self.app.client.get_current_wallet()
                stats = client.get_workspace_stats(wallet.address)
                files = stats.get("files", [])

                def update():
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
                    self.pub_file_table.data = data

                self.app.loop.call_soon_threadsafe(update)
            except Exception as e:
                self.app.loop.call_soon_threadsafe(
                    setattr, self.status_label, "text", f"Error loading files: {e}"
                )

        threading.Thread(target=do_refresh, daemon=True).start()

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

        self.status_label.text = "Publishing..."
        self.publish_btn.enabled = False

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

        def do_publish():
            try:
                from shared.client_core.knowledge_client import (
                    KnowledgeMarketplaceClient, build_knowledge_publish_tx,
                )

                wallet = self.app.client.get_current_wallet()
                # Use the same wallet-derived AES key that was used to encrypt
                # the file chunks during indexing.  The smart node stores this
                # key so it can decrypt chunks on behalf of marketplace buyers
                # and return LLM-synthesized answers only (never raw text).
                marketplace_key = hashlib.sha256(wallet.privkey).digest()

                smart_url = self._get_smart_url()
                client = KnowledgeMarketplaceClient(smart_url)

                result = client.publish_listing(
                    seller_address=wallet.address,
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

                # Broadcast knowledge_publish TX
                tx_msg = ""
                try:
                    smart_node_id = self.selected_smart_node.get("node_id", "")
                    tx = build_knowledge_publish_tx(
                        seller_address=wallet.address,
                        listing_id=listing_id,
                        smart_node_id=smart_node_id,
                        title=title,
                        file_count=total_files,
                        chunk_count=total_chunks,
                        price_per_query=ppq,
                        purchase_price=pp,
                        private_key_hex=wallet.privkey.hex(),
                        public_key_hex=wallet.get_pubkey_hex(),
                    )
                    resp, status = self.app.client.send_raw_transaction(tx)
                    if status == 200:
                        tx_msg = f" | TX: {tx['tx_hash'][:12]}..."
                except Exception as tx_err:
                    print(f"[KNOWLEDGE] Publish TX error: {tx_err}", flush=True)

                msg = (f"Published! {total_files} files, {total_chunks} chunks, "
                       f"ID: {listing_id[:12]}...{tx_msg}")

                def done():
                    self.publish_btn.enabled = True
                    self.status_label.text = msg
                self.app.loop.call_soon_threadsafe(done)

            except Exception as e:
                error_msg = str(e)
                def err():
                    self.publish_btn.enabled = True
                    self.status_label.text = f"Publish error: {error_msg}"
                self.app.loop.call_soon_threadsafe(err)

        threading.Thread(target=do_publish, daemon=True).start()

    # === My Listings Handlers ===

    def _on_refresh_my_listings(self, widget):
        """Refresh the user's own listings."""
        if not self.selected_smart_node:
            return

        def do_refresh():
            try:
                from shared.client_core.knowledge_client import KnowledgeMarketplaceClient
                client = KnowledgeMarketplaceClient(self._get_smart_url())
                wallet = self.app.client.get_current_wallet()
                results = client.get_my_listings(wallet.address)
                self.my_listings = results

                def update():
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
                    self.my_table.data = data
                    self.status_label.text = f"{len(results)} listings"

                self.app.loop.call_soon_threadsafe(update)
            except Exception as e:
                self.app.loop.call_soon_threadsafe(
                    setattr, self.status_label, "text", f"Error: {e}"
                )

        threading.Thread(target=do_refresh, daemon=True).start()

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
        if self._my_selected_idx < 0 or self._my_selected_idx >= len(self.my_listings):
            return

        listing = self.my_listings[self._my_selected_idx]
        new_status = "paused" if listing.get("status") == "active" else "active"

        def do_update():
            try:
                from shared.client_core.knowledge_client import KnowledgeMarketplaceClient
                client = KnowledgeMarketplaceClient(self._get_smart_url())
                wallet = self.app.client.get_current_wallet()
                client.update_listing(
                    listing["listing_id"], wallet.address, status=new_status
                )
                self.app.loop.call_soon_threadsafe(
                    setattr, self.status_label, "text",
                    f"Listing {new_status}"
                )
                self.app.loop.call_soon_threadsafe(self._on_refresh_my_listings, None)
            except Exception as e:
                self.app.loop.call_soon_threadsafe(
                    setattr, self.status_label, "text", f"Error: {e}"
                )

        threading.Thread(target=do_update, daemon=True).start()

    def _on_unpublish_listing(self, widget):
        """Delete/unpublish selected listing."""
        if self._my_selected_idx < 0 or self._my_selected_idx >= len(self.my_listings):
            return

        listing = self.my_listings[self._my_selected_idx]
        self.status_label.text = "Unpublishing..."

        def do_delete():
            try:
                from shared.client_core.knowledge_client import KnowledgeMarketplaceClient
                client = KnowledgeMarketplaceClient(self._get_smart_url())
                wallet = self.app.client.get_current_wallet()
                client.delete_listing(listing["listing_id"], wallet.address)
                self.app.loop.call_soon_threadsafe(
                    setattr, self.status_label, "text", "Listing unpublished."
                )
                self.app.loop.call_soon_threadsafe(self._on_refresh_my_listings, None)
            except Exception as e:
                self.app.loop.call_soon_threadsafe(
                    setattr, self.status_label, "text", f"Error: {e}"
                )

        threading.Thread(target=do_delete, daemon=True).start()
