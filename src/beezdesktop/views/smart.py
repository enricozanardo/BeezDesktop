"""
Smart View -- RAG Query Interface

Provides a UI for interacting with BeezSmart nodes:
- Query input with answer display and source citations
- Workspace file list showing indexed files
- Index toggle per file (index/remove from smart node)
- Smart node selection and pricing display
"""

import logging
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import asyncio
import hashlib

from shared.client_core.encryption import derive_encryption_key
from beezdesktop.theme import Colors, Font, Spacing, page_header, LoadingIndicator
from beezdesktop.views.lifecycle import ViewLifecycle

logger = logging.getLogger("beezdesktop.smart")

# Short timeout for status-only HTTP calls. Long-running ops (index, query)
# get their own client instance with the default 120s SmartNodeClient timeout.
_STATUS_TIMEOUT_S = 5


def _extract_pdf_text(file_path: str) -> str:
    """Extract text content from a PDF file using PyMuPDF.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text as a single string.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError(
            "PyMuPDF is required for PDF indexing. "
            "Install it with: pip install pymupdf"
        )

    text_parts = []
    with fitz.open(file_path) as doc:
        for page_num, page in enumerate(doc):
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(f"[Page {page_num + 1}]\n{page_text}")

    return "\n\n".join(text_parts)


class SmartView(ViewLifecycle):
    """RAG query interface for BeezSmart nodes."""

    def __init__(self, app):
        ViewLifecycle.__init__(self, app)
        self.selected_smart_node = None
        self.smart_nodes = []
        self.workspace_files = []
        self._busy = False

    def build(self) -> toga.Box:
        """Build the smart view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        container.add(page_header("BeezSmart", "Query your documents using AI-powered retrieval"))

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

        # Smart node selector
        node_section = self._build_node_selector()
        container.add(node_section)

        # Loading indicator
        self._loading = LoadingIndicator("Loading...")
        container.add(self._loading.box)

        # Query section
        query_section = self._build_query_section()
        container.add(query_section)

        # Answer display
        answer_section = self._build_answer_section()
        container.add(answer_section)

        # Workspace section
        workspace_section = self._build_workspace_section()
        container.add(workspace_section)

        # Load smart nodes from consensus
        self._load_smart_nodes()

        # B-15: restore any in-flight or completed query that was started
        # before this view instance existed (i.e. user navigated away and
        # back). The worker thread keeps running across navigation; only
        # the view is rebuilt.
        self._restore_query_from_state()

        return container

    def _restore_query_from_state(self) -> None:
        """Pre-fill the query UI from the persistent app-level state."""
        snap = self.app.query_states.smart.snapshot()
        status = snap.get("status", "idle")
        if status == "idle":
            return

        # Always restore the user's question text.
        try:
            self.query_input.value = snap.get("query_text", "")
        except Exception:
            pass

        if status == "running":
            self._set_busy(True, "Query running in background...")
            self.query_btn.enabled = False
            self.query_status.text = "Query running -- you may navigate away."
            # Start a polling task that watches the state and updates the UI
            # the moment the worker finishes. spawn_task ensures the poll
            # is cancelled when this view is destroyed (a fresh build will
            # spawn a new poll).
            self.spawn_task(self._poll_query_state(), name="poll_query")
        elif status == "done" and snap.get("result"):
            self._display_result(snap["result"])
        elif status == "error":
            self._display_error(snap.get("error_msg") or "Unknown error")

    async def _poll_query_state(self) -> None:
        """Poll app.query_states.smart until status leaves ``running``."""
        import asyncio as _asyncio
        try:
            while not self._destroyed:
                await _asyncio.sleep(0.5)
                snap = self.app.query_states.smart.snapshot()
                if snap["status"] == "done" and snap.get("result"):
                    self._display_result(snap["result"])
                    return
                if snap["status"] == "error":
                    self._display_error(snap.get("error_msg") or "Unknown error")
                    return
                if snap["status"] == "idle":
                    # User cleared the state externally; just stop.
                    return
        except _asyncio.CancelledError:
            raise

    def _set_busy(self, busy: bool, message: str = "Loading..."):
        """Show/hide the loading indicator."""
        self._busy = busy
        try:
            if busy:
                self._loading.show(message)
            else:
                self._loading.hide()
        except Exception:
            pass

    def _build_node_selector(self) -> toga.Box:
        """Build the smart node selection section."""
        box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 0, 15, 0)))

        label = toga.Label(
            "Smart Node",
            style=Pack(padding=(0, 0, 5, 0), font_weight="bold"),
        )
        box.add(label)

        row = toga.Box(style=Pack(direction=ROW))

        self.node_select = toga.Selection(
            items=["Loading smart nodes..."],
            on_change=self._on_node_selected,
            style=Pack(flex=1, padding_right=10),
        )
        row.add(self.node_select)

        self.node_info_label = toga.Label(
            "",
            style=Pack(padding=(5, 0), font_size=10, color="#666666"),
        )
        row.add(self.node_info_label)

        box.add(row)
        return box

    def _build_query_section(self) -> toga.Box:
        """Build the query input section."""
        box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 0, 15, 0)))

        label = toga.Label(
            "Ask a Question",
            style=Pack(padding=(0, 0, 5, 0), font_weight="bold"),
        )
        box.add(label)

        self.query_input = toga.MultilineTextInput(
            placeholder="Enter your question about your documents...",
            style=Pack(height=80, padding=(0, 0, 10, 0)),
        )
        box.add(self.query_input)

        # Options row
        options_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))

        options_row.add(
            toga.Label("Results:", style=Pack(padding=(5, 10, 0, 0), font_size=11))
        )
        self.top_k_select = toga.Selection(
            items=["1", "3", "5", "8", "10"],
            style=Pack(width=60),
        )
        self.top_k_select.value = "5"
        options_row.add(self.top_k_select)

        options_row.add(toga.Box(style=Pack(flex=1)))

        self.query_btn = toga.Button(
            "Ask",
            on_press=self._on_query,
            style=Pack(
                padding=10,
                width=120,
                background_color="#0d6efd",
                color="#ffffff",
            ),
        )
        options_row.add(self.query_btn)

        box.add(options_row)

        # Status label
        self.query_status = toga.Label(
            "",
            style=Pack(padding=(0, 0, 5, 0), font_size=10, color="#666666"),
        )
        box.add(self.query_status)

        return box

    def _build_answer_section(self) -> toga.Box:
        """Build the answer display section."""
        box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 0, 15, 0)))

        label = toga.Label(
            "Answer",
            style=Pack(padding=(0, 0, 5, 0), font_weight="bold"),
        )
        box.add(label)

        self.answer_display = toga.MultilineTextInput(
            readonly=True,
            placeholder="Answer will appear here...",
            style=Pack(height=150, padding=(0, 0, 5, 0)),
        )
        box.add(self.answer_display)

        # Sources display
        self.sources_label = toga.Label(
            "",
            style=Pack(padding=(0, 0, 5, 0), font_size=10, color="#444444"),
        )
        box.add(self.sources_label)

        return box

    def _build_workspace_section(self) -> toga.Box:
        """Build the workspace file list section."""
        box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 0, 15, 0)))

        header_row = toga.Box(style=Pack(direction=ROW))
        label = toga.Label(
            "Indexed Files",
            style=Pack(padding=(0, 0, 5, 0), font_weight="bold", flex=1),
        )
        header_row.add(label)

        refresh_btn = toga.Button(
            "Refresh",
            on_press=self._on_refresh_workspace,
            style=Pack(padding=5, width=80),
        )
        header_row.add(refresh_btn)

        index_btn = toga.Button(
            "Index File",
            on_press=self._on_index_file,
            style=Pack(padding=5, width=100, background_color="#198754", color="#ffffff"),
        )
        header_row.add(index_btn)

        self.remove_btn = toga.Button(
            "Remove File",
            on_press=self._on_remove_file,
            style=Pack(padding=5, width=110, background_color="#dc3545", color="#ffffff"),
            enabled=False,
        )
        header_row.add(self.remove_btn)

        box.add(header_row)

        # Workspace stats
        self.workspace_stats_label = toga.Label(
            "No files indexed yet",
            style=Pack(padding=(5, 0), font_size=11, color="#666666"),
        )
        box.add(self.workspace_stats_label)

        # Parallel list that keeps track of file_id per row
        self._file_ids: list = []
        self._selected_file_idx: int = -1

        # File table
        self.file_table = toga.Table(
            headings=["File Name", "Chunks", "Indexed At"],
            on_select=self._on_file_table_select,
            style=Pack(height=150, padding=(5, 0)),
        )
        box.add(self.file_table)

        return box

    # === Event Handlers ===

    def _load_smart_nodes(self):
        """Load available smart nodes from consensus.

        Uses ``state.smart_nodes`` which is populated by the consensus
        listener via ``ClientState.update_from_consensus()``.
        """
        if not self.app.state:
            return

        try:
            # Primary source: the pre-filtered smart_nodes list from ClientState
            self.smart_nodes = list(getattr(self.app.state, "smart_nodes", []))

            # Fallback: filter directly from raw consensus if smart_nodes empty
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
                    node_id = n.get("node_id", "unknown")
                    ip = n.get("ip", "unknown")
                    pe = n.get("price_per_embedding", "?")
                    pq = n.get("price_per_query", "?")
                    items.append(f"{node_id[:16]}.. ({ip}) | {pe}/{pq} BZT")
                self.node_select.items = items
                self.selected_smart_node = self.smart_nodes[0]
                self._update_node_info()
            else:
                self.node_select.items = ["No smart nodes available"]
        except Exception as e:
            logger.error(f"[SMART VIEW] Error loading nodes: {e}")
            import traceback; traceback.print_exc()
            self.node_select.items = ["Error loading nodes"]

    def _on_node_selected(self, widget):
        """Handle smart node selection change."""
        try:
            idx = self.node_select.items.index(widget.value)
            if idx < len(self.smart_nodes):
                self.selected_smart_node = self.smart_nodes[idx]
                self._update_node_info()
        except (ValueError, IndexError):
            pass

    def _update_node_info(self):
        """Update the node info display with pricing."""
        if self.selected_smart_node:
            pe = self.selected_smart_node.get("price_per_embedding", "?")
            pq = self.selected_smart_node.get("price_per_query", "?")
            self.node_info_label.text = f"Embedding: {pe} BZT/chunk | Query: {pq} BZT"

    def _on_query(self, widget):
        """Handle query button press."""
        if self._busy:
            return
        query_text = self.query_input.value
        if not query_text or not query_text.strip():
            self.query_status.text = "Please enter a question."
            return

        if not self.selected_smart_node:
            self.query_status.text = "Please select a smart node."
            return

        self.query_btn.enabled = False
        self.answer_display.value = ""
        self.sources_label.text = ""
        self._set_busy(True, "Processing query...")

        # Snapshot all UI/state values on the main thread so the worker
        # never touches Toga widgets after destruction.
        node_snapshot = dict(self.selected_smart_node)
        wallet = self.app.client.get_current_wallet()
        wallet_addr = wallet.address
        wallet_privkey = wallet.privkey.hex()
        wallet_pubkey = wallet.get_pubkey_hex()
        wallet_key = derive_encryption_key(wallet)
        top_k = int(self.top_k_select.value or "5")
        query_text_clean = query_text.strip()

        # B-15: mark query as running on the app-level state so a new
        # SmartView instance built by navigating back can find it.
        qstate = self.app.query_states.smart
        qstate.begin(
            query_text=query_text_clean,
            extra={
                "smart_node_id": node_snapshot.get("node_id", ""),
                "smart_node_ip": node_snapshot.get("ip", ""),
                "top_k": top_k,
            },
        )

        def do_query():
            try:
                from shared.client_core.docker_mapping import resolve_node_address
                from shared.client_core.smart_client import SmartNodeClient

                ip = node_snapshot.get("ip", "smart1")
                host_ip, port = resolve_node_address(ip, use_zmq=False)
                smart_url = f"http://{host_ip}:{port}"

                client = SmartNodeClient(smart_url)
                result = client.query(
                    query_text=query_text_clean,
                    decryption_key=wallet_key,
                    wallet_address=wallet_addr,
                    top_k=top_k,
                )

                # Broadcast smart_query transaction to blockchain
                try:
                    from shared.client_core.smart_client import build_smart_query_tx
                    smart_node_id = node_snapshot.get("node_id", "")
                    smart_node_wallet = node_snapshot.get("wallet_address", "")
                    query_hash = result.get("query_hash", hashlib.sha256(query_text_clean.encode()).hexdigest())
                    answer_hash = result.get("answer_hash", "")
                    file_ids = [s.get("file_id", "") for s in result.get("sources", []) if s.get("file_id")]
                    file_ids = list(set(file_ids)) if file_ids else []
                    query_cost = result.get("cost", 0)

                    tx = build_smart_query_tx(
                        wallet_address=wallet_addr,
                        query_hash=query_hash,
                        answer_hash=answer_hash,
                        smart_node_id=smart_node_id,
                        smart_node_wallet=smart_node_wallet,
                        cost=float(query_cost),
                        file_ids=file_ids,
                        private_key_hex=wallet_privkey,
                        public_key_hex=wallet_pubkey,
                    )
                    resp, status = self.app.client.send_raw_transaction(tx)
                    if status == 200:
                        result["tx_hash"] = tx["tx_hash"]
                    else:
                        logger.error(f"[SMART VIEW] smart_query TX failed: {resp}")
                except Exception as tx_err:
                    logger.error(f"[SMART VIEW] smart_query TX error: {tx_err}")

                # Persist BEFORE notifying the (possibly dead) view.
                qstate.succeed(result)
                self.safe_ui_call(self._display_result, result)
            except Exception as e:
                err_msg = str(e)
                qstate.fail(err_msg)
                self.safe_ui_call(self._display_error, err_msg)

        self.spawn_worker(do_query, name="query")

    def _display_result(self, result):
        """Display query result in the UI."""
        self._set_busy(False)
        self.query_btn.enabled = True
        answer = result.get("answer", "No answer received.")
        self.answer_display.value = answer

        sources = result.get("sources", [])
        if sources:
            parts = []
            for s in sources:
                parts.append(
                    f"[{s['source_num']}] File {s['file_id'][:8]}... "
                    f"chunk {s['chunk_index']} (relevance: {s['similarity']:.2f})"
                )
            self.sources_label.text = "Sources: " + " | ".join(parts)
        else:
            self.sources_label.text = ""

        cost = result.get("cost", 0)
        no_data = result.get("no_relevant_data", False)
        tx_hash = result.get("tx_hash", "")
        status = f"Cost: {cost} BZT"
        if no_data:
            status += " (no relevant data found)"
        if tx_hash:
            status += f" | TX: {tx_hash[:12]}..."
        self.query_status.text = status

    def _display_error(self, error_msg):
        """Display error message."""
        self._set_busy(False)
        self.query_btn.enabled = True
        self.query_status.text = f"Error: {error_msg}"

    def _on_index_file(self, widget):
        """Handle 'Index File' button -- index a file for RAG."""
        if not self.selected_smart_node:
            self.workspace_stats_label.text = "Select a smart node first."
            return

        if not self.app.client or not self.app.client.is_wallet_connected():
            self.workspace_stats_label.text = "Connect wallet first."
            return

        self.workspace_stats_label.text = "Select a file to index..."

        # Use Toga 0.4+ async dialog API; track the task in lifecycle so
        # it is cancelled if the user navigates away mid-dialog.
        try:
            dialog = toga.OpenFileDialog(
                title="Select a file to index for RAG",
                file_types=[
                    "txt", "md", "py", "json", "csv", "log", "rst",
                    "xml", "html", "yaml", "yml", "toml", "pdf",
                ],
            )
            task = self.spawn_task(self.app.main_window.dialog(dialog),
                                   name="open_file_dialog")
            if task is not None:
                task.add_done_callback(self._on_file_selected_for_index)
        except Exception as e:
            self.workspace_stats_label.text = f"Error opening file dialog: {e}"

    def _on_file_selected_for_index(self, task):
        """Handle file selection for indexing.

        Args:
            task: Completed asyncio.Task whose result is the selected Path or None.
        """
        try:
            result = task.result()
        except Exception as e:
            self.workspace_stats_label.text = f"File dialog error: {e}"
            return

        if not result:
            self.workspace_stats_label.text = "No file selected."
            return

        file_path = str(result)
        self._set_busy(True, f"Indexing {file_path.split('/')[-1].split(chr(92))[-1]}...")

        # Snapshot UI/state values before spawning the worker
        node_snapshot = dict(self.selected_smart_node)
        wallet = self.app.client.get_current_wallet()
        wallet_addr = wallet.address
        wallet_privkey = wallet.privkey.hex()
        wallet_pubkey = wallet.get_pubkey_hex()
        wallet_key = derive_encryption_key(wallet)

        def do_index():
            try:
                import uuid as _uuid

                if file_path.lower().endswith(".pdf"):
                    content = _extract_pdf_text(file_path)
                else:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                if not content or not content.strip():
                    self.safe_ui_call(self._set_workspace_stats_text,
                                      "File is empty or could not extract text.")
                    return

                from shared.client_core.docker_mapping import resolve_node_address
                from shared.client_core.smart_client import SmartNodeClient

                ip = node_snapshot.get("ip", "smart1")
                host_ip, port = resolve_node_address(ip, use_zmq=False)
                smart_url = f"http://{host_ip}:{port}"

                client = SmartNodeClient(smart_url)

                file_id = str(_uuid.uuid4())
                file_name = file_path.split("/")[-1].split("\\")[-1]

                result = client.index_file(
                    file_id=file_id,
                    file_name=file_name,
                    plaintext_content=content,
                    encryption_key=wallet_key,
                    wallet_address=wallet_addr,
                )

                chunks = result.get("chunks_indexed", 0)
                cost = result.get("total_cost", 0)
                smart_node_id = result.get("smart_node_id", "")

                tx_msg = ""
                try:
                    from shared.client_core.smart_client import build_smart_index_tx
                    smart_node_wallet = node_snapshot.get("wallet_address", "")
                    tx = build_smart_index_tx(
                        wallet_address=wallet_addr,
                        file_id=file_id,
                        smart_node_id=smart_node_id,
                        smart_node_wallet=smart_node_wallet,
                        num_chunks_indexed=chunks,
                        total_cost=cost,
                        private_key_hex=wallet_privkey,
                        public_key_hex=wallet_pubkey,
                    )
                    resp, status = self.app.client.send_raw_transaction(tx)
                    if status == 200:
                        tx_msg = f" | TX: {tx['tx_hash'][:12]}..."
                    else:
                        tx_msg = f" | TX failed: {resp.get('error', 'unknown')}"
                except Exception as tx_err:
                    tx_msg = f" | TX error: {tx_err}"
                    logger.error(f"[SMART VIEW] smart_index TX error: {tx_err}")

                msg = f"Indexed {file_name}: {chunks} chunks, cost {cost:.2f} BZT{tx_msg}"
                self.safe_ui_call(self._after_index_or_remove, msg)

            except Exception as e:
                err_msg = str(e)
                self.safe_ui_call(self._after_index_or_remove, f"Indexing error: {err_msg}")

        self.spawn_worker(do_index, name="index_file")

    def _on_file_table_select(self, widget):
        """Handle file table row selection."""
        try:
            if widget.selection is not None:
                # Find the index of the selected row
                for idx, row in enumerate(self.file_table.data):
                    if row == widget.selection:
                        self._selected_file_idx = idx
                        self.remove_btn.enabled = True
                        return
            self._selected_file_idx = -1
            self.remove_btn.enabled = False
        except Exception:
            self._selected_file_idx = -1
            self.remove_btn.enabled = False

    def _on_remove_file(self, widget):
        """Handle 'Remove File' button -- remove an indexed file from the smart node."""
        if self._selected_file_idx < 0 or self._selected_file_idx >= len(self._file_ids):
            self.workspace_stats_label.text = "Select a file to remove first."
            return

        if not self.selected_smart_node:
            self.workspace_stats_label.text = "Select a smart node first."
            return

        file_id = self._file_ids[self._selected_file_idx]
        # Get the file name for display
        try:
            file_name = self.file_table.data[self._selected_file_idx][0]
        except (IndexError, TypeError):
            file_name = file_id[:12]

        self.remove_btn.enabled = False
        self._set_busy(True, f"Removing {file_name}...")

        # Snapshot UI/state values
        node_snapshot = dict(self.selected_smart_node)
        wallet = self.app.client.get_current_wallet()
        wallet_addr = wallet.address

        def do_remove():
            try:
                from shared.client_core.docker_mapping import resolve_node_address
                from shared.client_core.smart_client import SmartNodeClient

                ip = node_snapshot.get("ip", "smart1")
                host_ip, port = resolve_node_address(ip, use_zmq=False)
                smart_url = f"http://{host_ip}:{port}"

                client = SmartNodeClient(smart_url)
                success = client.delete_file(file_id, wallet_addr)

                if success:
                    msg = f"Removed {file_name} successfully."
                else:
                    msg = f"Failed to remove {file_name} (not found or unauthorized)."

                self.safe_ui_call(self._after_index_or_remove, msg)

            except Exception as e:
                err_msg = str(e)
                self.safe_ui_call(self._after_index_or_remove, f"Remove error: {err_msg}")

        self.spawn_worker(do_remove, name="remove_file")

    def _set_workspace_stats_text(self, text: str) -> None:
        """Helper to update workspace_stats_label safely from a worker."""
        try:
            self.workspace_stats_label.text = text
        except Exception:
            pass

    def _after_index_or_remove(self, msg: str) -> None:
        """Common post-mutation flow: clear busy, set status, refresh workspace."""
        self._set_busy(False)
        self._set_workspace_stats_text(msg)
        self._refresh_workspace()

    def _on_refresh_workspace(self, widget=None):
        """Refresh workspace file list (button handler)."""
        self._refresh_workspace()

    def _refresh_workspace(self):
        """Fetch and display workspace statistics off the main thread.

        Previously this method ran the HTTP call synchronously on the Toga
        main thread with timeout=10s, freezing the entire UI. Now it spawns
        a worker via the lifecycle and updates widgets only via safe_ui_call.
        """
        if not self.selected_smart_node:
            return
        if self._destroyed:
            return

        node_snapshot = dict(self.selected_smart_node)
        wallet = self.app.client.get_current_wallet()
        if wallet is None:
            return
        wallet_addr = wallet.address

        def do_refresh():
            try:
                from shared.client_core.docker_mapping import resolve_node_address
                from shared.client_core.smart_client import SmartNodeClient

                ip = node_snapshot.get("ip", "smart1")
                host_ip, port = resolve_node_address(ip, use_zmq=False)
                smart_url = f"http://{host_ip}:{port}"

                client = SmartNodeClient(smart_url, timeout=_STATUS_TIMEOUT_S)
                stats = client.get_workspace_stats(wallet_addr)
                self.safe_ui_call(self._apply_workspace_stats, stats)
            except Exception as exc:
                err_msg = str(exc)
                self.safe_ui_call(self._set_workspace_stats_text,
                                  f"Error loading workspace: {err_msg}")

        self.spawn_worker(do_refresh, name="refresh_workspace")

    def _apply_workspace_stats(self, stats: dict) -> None:
        """Render workspace stats - runs on the main thread via safe_ui_call."""
        try:
            total_files = stats.get("total_files", 0)
            total_chunks = stats.get("total_chunks", 0)
            total_queries = stats.get("total_queries", 0)

            self.workspace_stats_label.text = (
                f"{total_files} files, {total_chunks} chunks indexed, "
                f"{total_queries} queries made"
            )

            files = stats.get("files", [])
            data = []
            self._file_ids = []
            for f in files:
                data.append((
                    f.get("file_name", "unknown"),
                    str(f.get("num_chunks", 0)),
                    (f.get("indexed_at", "")[:19] if f.get("indexed_at") else ""),
                ))
                self._file_ids.append(f.get("file_id", ""))
            self.file_table.data = data
            self._selected_file_idx = -1
            self.remove_btn.enabled = False
        except Exception as exc:
            logger.error(f"[SMART VIEW] _apply_workspace_stats error: {exc}")
