"""
Blockchain View

Blockchain explorer: view blocks, transactions, wallet lookup.
Similar to BeezFE's BlockchainPage with drill-down capabilities.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import asyncio

from beezdesktop.theme import Colors, Font, Spacing, page_header


class BlockchainView:
    """Blockchain explorer view with auto-refresh."""
    
    def __init__(self, app):
        self.app = app
        self.search_input = None
        self.info_labels = {}
        self.blocks_table = None
        self.current_offset = 0
        self.blocks_per_page = 10
        self._block_heights = []
        
        # Current block details for transaction drill-down
        self._current_block = None
        self._current_block_txs = []
        
        # Auto-refresh settings
        self._auto_refresh_enabled = True
        self._auto_refresh_interval = 30  # seconds
        self._refresh_task = None
    
    def build(self) -> toga.Box:
        """Build the blockchain view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        container.add(page_header("Blockchain Explorer", "Browse blocks and transactions"))
        
        # Info section
        info_section = self._build_info_section()
        container.add(info_section)
        
        # Search section
        search_section = self._build_search_section()
        container.add(search_section)
        
        # Blocks section
        blocks_section = self._build_blocks_section()
        container.add(blocks_section)
        
        # Load data
        asyncio.create_task(self._load_blockchain_info())
        asyncio.create_task(self._load_blocks())
        
        # Start auto-refresh
        if self._auto_refresh_enabled:
            self._refresh_task = asyncio.create_task(self._auto_refresh_loop())
        
        return container
    
    async def _auto_refresh_loop(self):
        """Auto-refresh blockchain data periodically."""
        try:
            while self._auto_refresh_enabled:
                await asyncio.sleep(self._auto_refresh_interval)
                if not self._auto_refresh_enabled:
                    break
                try:
                    await self._load_blockchain_info()
                    # Only refresh blocks if on first page
                    if self.current_offset == 0:
                        await self._load_blocks()
                except Exception as e:
                    print(f"[BLOCKCHAIN] Auto-refresh error: {e}", flush=True)
        except asyncio.CancelledError:
            pass  # Task cancelled on view switch -- expected
    
    def _build_info_section(self) -> toga.Box:
        """Build the blockchain info section."""
        section = toga.Box(
            style=Pack(direction=COLUMN, padding=Spacing.CARD_PADDING, background_color=Colors.SURFACE_INFO)
        )
        
        header_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, Spacing.SM, 0)))
        
        header = toga.Label(
            "Blockchain Status",
            style=Pack(font_size=Font.SIZE_H3, font_weight="bold", color=Colors.TEXT_PRIMARY, flex=1)
        )
        header_row.add(header)
        
        refresh_btn = toga.Button(
            "Refresh",
            on_press=lambda w: asyncio.create_task(self._load_blockchain_info()),
            style=Pack(width=80, padding=(0, 5, 0, 0))
        )
        header_row.add(refresh_btn)
        
        # Auto-refresh indicator
        self.auto_refresh_label = toga.Label(
            "Auto: ON",
            style=Pack(padding=(5, 0, 0, 5), font_size=10, color="#2e7d32")
        )
        header_row.add(self.auto_refresh_label)
        
        section.add(header_row)
        
        # Info grid
        info_grid = toga.Box(style=Pack(direction=ROW, padding=5))
        
        info_items = [
            ("block_height", "Block Height"),
            ("mempool_size", "Pending TXs"),
            ("total_wallets", "Total Wallets"),
        ]
        
        for key, label_text in info_items:
            card = toga.Box(style=Pack(direction=COLUMN, padding=10, width=150))
            value_label = toga.Label("--", style=Pack(font_size=20, font_weight="bold"))
            self.info_labels[key] = value_label
            card.add(value_label)
            card.add(toga.Label(label_text, style=Pack(font_size=11, color="#666666")))
            info_grid.add(card)
        
        section.add(info_grid)
        
        return section
    
    def _build_search_section(self) -> toga.Box:
        """Build the search section."""
        section = toga.Box(
            style=Pack(direction=COLUMN, padding=10)
        )
        
        header = toga.Label(
            "Search",
            style=Pack(font_size=14, font_weight="bold", padding=(10, 0, 5, 0))
        )
        section.add(header)
        
        # Search row
        search_row = toga.Box(style=Pack(direction=ROW, padding=5))
        
        self.search_input = toga.TextInput(
            placeholder="Enter wallet address (bez...) or block height...",
            style=Pack(flex=1, padding=(0, 10, 0, 0))
        )
        search_row.add(self.search_input)
        
        search_btn = toga.Button(
            "Search",
            on_press=self._on_search,
            style=Pack(width=80)
        )
        search_row.add(search_btn)
        
        section.add(search_row)
        
        # Search result area
        self.search_result_box = toga.Box(style=Pack(direction=COLUMN, padding=5))
        section.add(self.search_result_box)
        
        return section
    
    def _build_blocks_section(self) -> toga.Box:
        """Build the blocks list section."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        
        header = toga.Label(
            "Latest Blocks",
            style=Pack(font_size=14, font_weight="bold", padding=(10, 0, 10, 0))
        )
        section.add(header)
        
        # Blocks table
        self.blocks_table = toga.Table(
            headings=["Height", "Hash", "Transactions", "Timestamp"],
            data=[],
            style=Pack(flex=1),
            on_select=self._on_block_selected
        )
        section.add(self.blocks_table)
        
        # Pagination
        pagination_row = toga.Box(style=Pack(direction=ROW, padding=(10, 0, 0, 0)))
        
        prev_btn = toga.Button(
            "← Previous",
            on_press=self._on_prev_page,
            style=Pack(width=100)
        )
        pagination_row.add(prev_btn)
        
        self.page_label = toga.Label(
            "Page 1",
            style=Pack(flex=1, padding=(5, 10, 5, 10))
        )
        pagination_row.add(self.page_label)
        
        next_btn = toga.Button(
            "Next →",
            on_press=self._on_next_page,
            style=Pack(width=100)
        )
        pagination_row.add(next_btn)
        
        section.add(pagination_row)
        
        return section
    
    async def _load_blockchain_info(self):
        """Load blockchain info from API."""
        if not self.app.client:
            return
        
        loop = asyncio.get_event_loop()
        result, status = await loop.run_in_executor(
            None, self.app.client.get_blockchain_info
        )
        
        if status == 200:
            blockchain = result.get("blockchain", result)
            self.info_labels["block_height"].text = str(blockchain.get("current_block", "--"))
            self.info_labels["mempool_size"].text = str(blockchain.get("mempool_size", "--"))
            self.info_labels["total_wallets"].text = str(blockchain.get("total_wallets", "--"))
        else:
            print(f"[BLOCKCHAIN] Info error: {result.get('error', 'Unknown')}", flush=True)
    
    async def _load_blocks(self):
        """Load blocks from API."""
        if not self.app.client or not self.blocks_table:
            return
        
        loop = asyncio.get_event_loop()
        result, status = await loop.run_in_executor(
            None,
            lambda: self.app.client.get_blocks(self.blocks_per_page, self.current_offset)
        )
        
        self.blocks_table.data.clear()
        self._block_heights = []
        
        if status == 200:
            blocks = result.get("blocks", [])
            
            for block in blocks:
                height = str(block.get("height", block.get("block_height", "--")))
                self._block_heights.append(height)
                
                block_hash = block.get("hash", block.get("block_hash", ""))
                short_hash = f"{block_hash[:8]}...{block_hash[-8:]}" if len(block_hash) > 16 else block_hash
                
                timestamp = block.get("timestamp", "")
                if isinstance(timestamp, dict):
                    timestamp = timestamp.get("timestamp", "")
                if timestamp and len(str(timestamp)) > 19:
                    timestamp = str(timestamp)[:19]
                
                tx_count = block.get("tx_count", block.get("transaction_count", 0))
                
                self.blocks_table.data.append([
                    height,
                    short_hash,
                    str(tx_count),
                    str(timestamp)
                ])
            
            # Update page label
            page_num = (self.current_offset // self.blocks_per_page) + 1
            self.page_label.text = f"Page {page_num}"
        else:
            error = result.get('error', 'Unknown')
            print(f"[BLOCKCHAIN] Blocks error: {error}", flush=True)
            self.blocks_table.data.append(["--", f"Error: {error[:30]}", "--", "--"])
    
    def _on_prev_page(self, widget):
        """Previous page of blocks."""
        if self.current_offset >= self.blocks_per_page:
            self.current_offset -= self.blocks_per_page
            asyncio.create_task(self._load_blocks())
    
    def _on_next_page(self, widget):
        """Next page of blocks."""
        self.current_offset += self.blocks_per_page
        asyncio.create_task(self._load_blocks())
    
    def _on_block_selected(self, widget):
        """Handle block selection."""
        try:
            selection = widget.selection
            if not selection:
                return

            height = None

            # Prefer direct column access (toga stores data in append order)
            try:
                val = selection[0]
                if val and str(val) not in ("--", "None", ""):
                    height = str(val)
            except (TypeError, IndexError, KeyError):
                pass

            # Fallback: parse from repr string for older toga versions
            if height is None:
                import re
                row_str = repr(selection)
                match = re.search(r"height='(\d+)'", row_str)
                if match:
                    height = match.group(1)

            if height and str(height) not in ("--", "None", ""):
                asyncio.create_task(self._show_block_details(str(height)))
        except (ValueError, AttributeError):
            # Silently ignore - happens when table data is refreshed during selection
            pass
        except Exception as e:
            print(f"[BLOCKCHAIN] Selection error: {e}", flush=True)
    
    def _truncate_hash(self, hash_str: str, length: int = 16) -> str:
        """Truncate hash for display."""
        if not hash_str or len(hash_str) <= length:
            return hash_str or "N/A"
        return f"{hash_str[:length//2]}...{hash_str[-length//2:]}"
    
    def _format_timestamp(self, timestamp) -> str:
        """Format timestamp for display."""
        if timestamp and isinstance(timestamp, dict):
            return timestamp.get("timestamp", "N/A")
        if isinstance(timestamp, str):
            return timestamp[:19] if len(timestamp) > 19 else timestamp
        return "N/A"
    
    async def _show_block_details(self, height: str):
        """Show detailed block dialog with transactions list."""
        if not self.app.client:
            return
        
        loop = asyncio.get_event_loop()
        result, status = await loop.run_in_executor(
            None,
            lambda: self.app.client.get_block_by_height(int(height))
        )
        
        if status != 200:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed to load block #{height}")
            )
            return
        
        block = result.get("block", result)
        self._current_block = block
        
        # Extract block information
        block_height = block.get("height", height)
        block_hash = block.get("hash", block.get("header", {}).get("hash", "N/A"))
        prev_hash = block.get("previous_hash", block.get("header", {}).get("previous_hash", 
                   block.get("header", {}).get("prev_hash", "N/A")))
        timestamp = block.get("timestamp", block.get("node", {}).get("timestamp", "N/A"))
        miner = block.get("miner", block.get("miner_address", 
               block.get("node", {}).get("miner_address", "N/A")))
        
        # Get transactions
        txs = block.get("txs", block.get("body", {}).get("txs", []))
        self._current_block_txs = txs
        
        # Build detailed block info
        details = (
            f"━━━ Block Information ━━━\n\n"
            f"Height: #{block_height}\n"
            f"Hash: {block_hash}\n"
            f"Previous Hash: {self._truncate_hash(prev_hash, 32)}\n"
            f"Timestamp: {self._format_timestamp(timestamp)}\n"
            f"Miner: {self._truncate_hash(miner, 24)}\n\n"
            f"━━━ Transactions ({len(txs)}) ━━━\n\n"
        )
        
        if not txs:
            details += "No transactions in this block.\n"
        else:
            for i, tx in enumerate(txs[:10]):  # Show first 10
                tx_type = tx.get("type", "transfer")
                tx_hash = tx.get("tx_hash", "")
                # Use asking_price for ownership txs, amount for others
                if tx_type in ("ownership_request", "ownership_accept"):
                    amount = tx.get("asking_price", "0")
                elif tx_type == "smart_index":
                    amount = tx.get("total_cost", "0")
                elif tx_type == "smart_query":
                    amount = tx.get("cost", "0")
                elif tx_type == "knowledge_query":
                    amount = tx.get("cost", "0")
                elif tx_type == "knowledge_purchase":
                    amount = tx.get("purchase_price", "0")
                elif tx_type == "knowledge_publish":
                    amount = "0"
                else:
                    amount = tx.get("amount", "0")
                
                # Get addresses based on type
                if tx_type == "upload":
                    from_addr = tx.get("uploader", "N/A")
                    to_addr = "Storage"
                elif tx_type == "ownership_request":
                    from_addr = tx.get("current_owner", "N/A")
                    to_addr = tx.get("new_owner", "N/A")
                elif tx_type == "ownership_accept":
                    from_addr = tx.get("new_owner", "N/A")
                    to_addr = "(accepted)"
                elif tx_type == "ownership_reject":
                    from_addr = tx.get("new_owner", "N/A")
                    to_addr = "(rejected)"
                elif tx_type == "ownership_cancel":
                    from_addr = tx.get("current_owner", "N/A")
                    to_addr = "(cancelled)"
                elif tx_type == "update_digital_asset_price":
                    from_addr = tx.get("owner_address", "N/A")
                    to_addr = f"Price → {tx.get('new_price', '?')}"
                    amount = tx.get("new_price", "0")
                elif tx_type == "update_digital_asset_visibility":
                    from_addr = tx.get("owner_address", "N/A")
                    to_addr = f"→ {tx.get('visibility', '?').upper()}"
                    amount = "0"
                elif tx_type == "update_asset_tags":
                    from_addr = tx.get("owner_address", "N/A")
                    to_addr = "Tags update"
                    amount = "0"
                elif tx_type == "penalty":
                    from_addr = tx.get("dam_address", "N/A")
                    to_addr = tx.get("target_node_address", "N/A")
                    amount = f"Score: {tx.get('penalty_score', '?')}"
                elif tx_type == "escrow_release":
                    from_addr = f"Escrow ({self._truncate_hash(tx.get('from_escrow', ''), 8)})"
                    to_addr = tx.get("recipient", "N/A")
                elif tx_type == "dam_verification_reward":
                    from_addr = f"Escrow ({self._truncate_hash(tx.get('from_escrow', ''), 8)})"
                    to_addr = tx.get("recipient", "N/A")
                elif tx_type == "escrow_unlock":
                    from_addr = tx.get("dam_address", "N/A")
                    to_addr = f"File ({self._truncate_hash(tx.get('file_id', ''), 8)})"
                    amount = "Unlock"
                elif tx_type == "datrone_reward":
                    from_addr = "Datrone"
                    to_addr = tx.get("recipient", "N/A")
                elif tx_type == "update_chunk_location":
                    from_addr = tx.get("old_node_id", "N/A")
                    to_addr = tx.get("new_node_id", "N/A")
                    amount = f"{len(tx.get('migrated_chunks', []))} chunks"
                elif tx_type == "smart_index":
                    from_addr = tx.get("wallet_address", "N/A")
                    to_addr = tx.get("smart_node_wallet", "N/A")
                    chunks = tx.get("num_chunks_indexed", 0)
                    amount = f"{tx.get('total_cost', 0)} BZT ({chunks} chunks)"
                elif tx_type == "smart_query":
                    from_addr = tx.get("wallet_address", "N/A")
                    to_addr = tx.get("smart_node_wallet", "N/A")
                    amount = f"{tx.get('cost', 0)} BZT"
                elif tx_type == "knowledge_publish":
                    from_addr = tx.get("seller_address", "N/A")
                    to_addr = f"Listing ({self._truncate_hash(tx.get('listing_id', ''), 8)})"
                    amount = "0 BZT"
                elif tx_type == "knowledge_query":
                    from_addr = tx.get("buyer_address", "N/A")
                    to_addr = tx.get("seller_address", "N/A")
                    amount = f"{tx.get('cost', 0)} BZT"
                elif tx_type == "knowledge_purchase":
                    from_addr = tx.get("buyer_address", "N/A")
                    to_addr = tx.get("seller_address", "N/A")
                    amount = f"{tx.get('purchase_price', 0)} BZT"
                else:
                    from_addr = tx.get("sender", "N/A")
                    to_addr = tx.get("recipient", "N/A")
                
                details += (
                    f"{i+1}. [{tx_type.upper()}] {self._truncate_hash(tx_hash, 16)}\n"
                    f"   From: {self._truncate_hash(from_addr, 16)} → To: {self._truncate_hash(to_addr, 16)}\n"
                    f"   Amount: {amount}\n\n"
                )
            
            if len(txs) > 10:
                details += f"... and {len(txs) - 10} more transactions\n"
        
        details += "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        details += "Tap 'View Transactions' to see all transaction details."
        
        # Show block details with option to view transactions
        if txs:
            result = await self.app.main_window.dialog(
                toga.QuestionDialog(
                    f"Block #{block_height}",
                    details + "\n\nView transaction list?"
                )
            )
            if result:
                await self._show_transactions_list(block_height, txs)
        else:
            await self.app.main_window.dialog(
                toga.InfoDialog(f"Block #{block_height}", details)
            )
    
    async def _show_transactions_list(self, block_height, txs):
        """Show list of transactions in a block."""
        if not txs:
            return
        
        # Build transaction selection list
        tx_options = []
        for i, tx in enumerate(txs):
            tx_type = tx.get("type", "transfer")
            tx_hash = tx.get("tx_hash", "unknown")
            if tx_type in ("ownership_request", "ownership_accept"):
                amount = tx.get("asking_price", "0")
            elif tx_type == "smart_index":
                amount = tx.get("total_cost", "0")
            elif tx_type in ("smart_query", "knowledge_query"):
                amount = tx.get("cost", "0")
            elif tx_type == "knowledge_purchase":
                amount = tx.get("purchase_price", "0")
            elif tx_type == "knowledge_publish":
                amount = "0"
            else:
                amount = tx.get("amount", "0")
            tx_options.append(f"{i+1}. [{tx_type}] {self._truncate_hash(tx_hash, 12)} - {amount}")
        
        # Ask which transaction to view
        prompt = (
            f"Block #{block_height} contains {len(txs)} transaction(s).\n\n"
            f"Enter transaction number (1-{len(txs)}) to view details:"
        )
        
        # Use a simple number input for selection
        for i, tx in enumerate(txs):
            view_more = await self.app.main_window.dialog(
                toga.QuestionDialog(
                    f"Transaction {i+1}/{len(txs)}",
                    self._format_transaction_details(tx, block_height) + 
                    "\n\nView next transaction?"
                )
            )
            if not view_more:
                break
    
    def _format_transaction_details(self, tx, block_height) -> str:
        """Format transaction details for display."""
        tx_type = tx.get("type", "transfer")
        tx_hash = tx.get("tx_hash", "N/A")
        if tx_type in ("ownership_request", "ownership_accept"):
            amount = tx.get("asking_price", "0")
        elif tx_type == "update_digital_asset_price":
            amount = tx.get("new_price", "0")
        elif tx_type in ("update_digital_asset_visibility", "update_asset_tags"):
            amount = "--"
        elif tx_type == "penalty":
            amount = f"Score: {tx.get('penalty_score', '?')}"
        elif tx_type == "update_chunk_location":
            amount = f"{len(tx.get('migrated_chunks', []))} chunks"
        elif tx_type == "smart_index":
            amount = f"{tx.get('total_cost', 0)} BZT"
        elif tx_type == "smart_query":
            amount = f"{tx.get('cost', 0)} BZT"
        elif tx_type == "knowledge_query":
            amount = f"{tx.get('cost', 0)} BZT"
        elif tx_type == "knowledge_purchase":
            amount = f"{tx.get('purchase_price', 0)} BZT"
        elif tx_type == "knowledge_publish":
            amount = "0 BZT"
        else:
            amount = tx.get("amount", "0")
        timestamp = self._format_timestamp(tx.get("timestamp", "N/A"))
        
        # Friendly display name for tx type
        type_labels = {
            "escrow_release": "STORAGE REWARD",
            "dam_verification_reward": "DAM REWARD",
            "penalty": "PENALTY",
            "update_chunk_location": "CHUNK MIGRATION",
            "datrone_reward": "DATRONE REWARD",
            "escrow_unlock": "ESCROW UNLOCK",
            "knowledge_publish": "KNOWLEDGE PUBLISH",
            "knowledge_query": "KNOWLEDGE QUERY",
            "knowledge_purchase": "KNOWLEDGE PURCHASE",
        }
        type_display = type_labels.get(tx_type, tx_type.upper().replace("UPDATE_DIGITAL_ASSET_", "").replace("_", " "))
        
        details = (
            f"━━━ Transaction Details ━━━\n\n"
            f"Hash: {tx_hash}\n"
            f"Type: {type_display}\n"
            f"Amount: {amount}\n"
            f"Block: #{block_height}\n"
            f"Timestamp: {timestamp}\n\n"
        )
        
        if tx_type == "upload":
            details += (
                f"━━━ Upload Details ━━━\n\n"
                f"Uploader: {tx.get('uploader', 'N/A')}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
                f"File Name: {tx.get('file_name', 'N/A')}\n"
                f"File Size: {tx.get('file_size', 'N/A')} bytes\n"
                f"Chunks: {tx.get('num_chunks', 'N/A')}\n"
                f"Guardian DAM: {self._truncate_hash(tx.get('guardian_dam_id', 'N/A'), 16)}\n"
            )
        elif tx_type == "rollback":
            details += (
                f"━━━ Rollback Details ━━━\n\n"
                f"Target TX: {self._truncate_hash(tx.get('target_tx_hash', 'N/A'), 24)}\n"
                f"From: {tx.get('recipient', 'N/A')}\n"
                f"To: {tx.get('sender', 'N/A')}\n"
            )
        elif tx_type == "freeze":
            details += (
                f"━━━ Freeze Details ━━━\n\n"
                f"Target: {tx.get('target_address', 'N/A')}\n"
                f"Duration: {tx.get('duration_blocks', 'N/A')} blocks\n"
                f"Reason: {tx.get('reason', 'N/A')}\n"
            )
        elif tx_type == "penalty":
            details += (
                f"━━━ Penalty Details ━━━\n\n"
                f"DAM Node: {self._truncate_hash(tx.get('dam_address', 'N/A'), 20)}\n"
                f"Target Node: {self._truncate_hash(tx.get('target_node_id', 'N/A'), 20)}\n"
                f"Target Address: {self._truncate_hash(tx.get('target_node_address', 'N/A'), 20)}\n"
                f"Penalty Score: {tx.get('penalty_score', 'N/A')}\n"
                f"Type: {tx.get('verification_type', 'N/A')}\n"
                f"Reason: {tx.get('reason', 'N/A')}\n"
                f"Evidence: {self._truncate_hash(tx.get('evidence_hash', 'N/A'), 20)}\n"
            )
        elif tx_type == "escrow_release":
            details += (
                f"━━━ Escrow Release Details ━━━\n\n"
                f"Escrow (File): {self._truncate_hash(tx.get('from_escrow', 'N/A'), 20)}\n"
                f"Recipient: {tx.get('recipient', 'N/A')}\n"
                f"Amount: {tx.get('amount', 'N/A')}\n"
                f"Release Block: {tx.get('release_block', 'N/A')}\n"
            )
        elif tx_type == "dam_verification_reward":
            details += (
                f"━━━ DAM Verification Reward ━━━\n\n"
                f"Escrow (File): {self._truncate_hash(tx.get('from_escrow', 'N/A'), 20)}\n"
                f"Recipient: {tx.get('recipient', 'N/A')}\n"
                f"Amount: {tx.get('amount', 'N/A')}\n"
                f"Verified Nodes: {tx.get('verified_count', 'N/A')}\n"
                f"Release Block: {tx.get('release_block', 'N/A')}\n"
            )
        elif tx_type == "escrow_unlock":
            details += (
                f"━━━ Escrow Unlock Details ━━━\n\n"
                f"DAM Guardian: {tx.get('dam_address', 'N/A')}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
                f"Release Block: {tx.get('release_block', 'N/A')}\n"
                f"Beneficiaries: {len(tx.get('verified_beneficiaries', []))}\n"
            )
        elif tx_type == "ownership_request":
            details += (
                f"━━━ Ownership Request ━━━\n\n"
                f"From (current owner): {tx.get('current_owner', 'N/A')}\n"
                f"To (new owner): {tx.get('new_owner', 'N/A')}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
                f"Asking Price: {tx.get('asking_price', '0')}\n"
                f"Message: {tx.get('ownership_message', '')}\n"
            )
        elif tx_type == "ownership_accept":
            details += (
                f"━━━ Ownership Accept ━━━\n\n"
                f"Accepted by (new owner): {tx.get('new_owner', 'N/A')}\n"
                f"Request ID: {self._truncate_hash(tx.get('request_id', 'N/A'), 20)}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
                f"Price Paid: {tx.get('asking_price', '0')}\n"
            )
        elif tx_type == "ownership_reject":
            details += (
                f"━━━ Ownership Reject ━━━\n\n"
                f"Rejected by: {tx.get('new_owner', 'N/A')}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
                f"Reason: {tx.get('ownership_message', 'No reason given')}\n"
            )
        elif tx_type == "ownership_cancel":
            details += (
                f"━━━ Ownership Cancel ━━━\n\n"
                f"Cancelled by: {tx.get('current_owner', 'N/A')}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
            )
        elif tx_type == "update_digital_asset_price":
            details += (
                f"━━━ Price Update ━━━\n\n"
                f"Owner: {tx.get('owner_address', 'N/A')}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
                f"New Price: {tx.get('new_price', 'N/A')}\n"
                f"Old Price: {tx.get('old_price', 'N/A')}\n"
                f"Reason: {tx.get('update_reason', 'N/A')}\n"
            )
        elif tx_type == "update_digital_asset_visibility":
            details += (
                f"━━━ Visibility Update ━━━\n\n"
                f"Owner: {tx.get('owner_address', 'N/A')}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
                f"Visibility: {tx.get('visibility', 'N/A').upper()}\n"
                f"Reason: {tx.get('update_reason', 'N/A')}\n"
            )
        elif tx_type == "update_asset_tags":
            details += (
                f"━━━ Tags Update ━━━\n\n"
                f"Owner: {tx.get('owner_address', 'N/A')}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
                f"Tags: {', '.join(tx.get('tags', []))}\n"
            )
        elif tx_type == "smart_index":
            details += (
                f"━━━ Smart Index Details ━━━\n\n"
                f"Payer: {tx.get('wallet_address', 'N/A')}\n"
                f"Smart Node: {tx.get('smart_node_id', 'N/A')}\n"
                f"Smart Wallet: {tx.get('smart_node_wallet', 'N/A')}\n"
                f"File ID: {self._truncate_hash(tx.get('file_id', 'N/A'), 20)}\n"
                f"Chunks Indexed: {tx.get('num_chunks_indexed', 'N/A')}\n"
                f"Cost: {tx.get('total_cost', 'N/A')} BZT\n"
            )
        elif tx_type == "smart_query":
            file_ids = tx.get('file_ids', []) or []
            details += (
                f"━━━ Smart Query Details ━━━\n\n"
                f"Payer: {tx.get('wallet_address', 'N/A')}\n"
                f"Smart Node: {tx.get('smart_node_id', 'N/A')}\n"
                f"Smart Wallet: {tx.get('smart_node_wallet', 'N/A')}\n"
                f"Query Hash: {self._truncate_hash(tx.get('query_hash', 'N/A'), 20)}\n"
                f"Answer Hash: {self._truncate_hash(tx.get('answer_hash', 'N/A'), 20)}\n"
                f"Files Queried: {len(file_ids)}\n"
                f"Cost: {tx.get('cost', 'N/A')} BZT\n"
            )
        elif tx_type == "knowledge_publish":
            details += (
                f"━━━ Knowledge Publish Details ━━━\n\n"
                f"Seller: {tx.get('seller_address', 'N/A')}\n"
                f"Listing ID: {tx.get('listing_id', 'N/A')}\n"
                f"Smart Node: {tx.get('smart_node_id', 'N/A')}\n"
                f"Title Hash: {self._truncate_hash(tx.get('title_hash', 'N/A'), 20)}\n"
                f"Files: {tx.get('file_count', 'N/A')}\n"
                f"Chunks: {tx.get('chunk_count', 'N/A')}\n"
                f"Price/Query: {tx.get('price_per_query', 'N/A')} BZT\n"
                f"Purchase Price: {tx.get('purchase_price', 0)} BZT\n"
            )
        elif tx_type == "knowledge_query":
            details += (
                f"━━━ Knowledge Query Details ━━━\n\n"
                f"Buyer: {tx.get('buyer_address', 'N/A')}\n"
                f"Seller: {tx.get('seller_address', 'N/A')}\n"
                f"Listing ID: {tx.get('listing_id', 'N/A')}\n"
                f"Smart Node: {tx.get('smart_node_id', 'N/A')}\n"
                f"Smart Wallet: {tx.get('smart_node_wallet', 'N/A')}\n"
                f"Query Hash: {self._truncate_hash(tx.get('query_hash', 'N/A'), 20)}\n"
                f"Answer Hash: {self._truncate_hash(tx.get('answer_hash', 'N/A'), 20)}\n"
                f"Cost: {tx.get('cost', 'N/A')} BZT\n"
            )
        elif tx_type == "knowledge_purchase":
            file_ids = tx.get('file_ids', []) or []
            details += (
                f"━━━ Knowledge Purchase Details ━━━\n\n"
                f"Buyer: {tx.get('buyer_address', 'N/A')}\n"
                f"Seller: {tx.get('seller_address', 'N/A')}\n"
                f"Listing ID: {tx.get('listing_id', 'N/A')}\n"
                f"Purchase Price: {tx.get('purchase_price', 'N/A')} BZT\n"
                f"Files Transferred: {len(file_ids)}\n"
            )
        else:
            # Normal transfer
            details += (
                f"━━━ Transfer Details ━━━\n\n"
                f"From: {tx.get('sender', 'N/A')}\n"
                f"To: {tx.get('recipient', 'N/A')}\n"
            )
        
        return details
    
    async def _on_search(self, widget):
        """Handle search."""
        query = self.search_input.value.strip()
        
        if not query:
            return
        
        # Clear previous results
        for child in list(self.search_result_box.children):
            self.search_result_box.remove(child)
        
        searching_label = toga.Label("Searching...", style=Pack(padding=5, color="#666666"))
        self.search_result_box.add(searching_label)
        
        if query.startswith("bez"):
            await self._search_wallet(query)
        elif len(query) == 64:  # Likely a hash
            await self._search_transaction(query)
        else:
            try:
                block_height = int(query)
                await self._search_block(block_height)
            except ValueError:
                await self._show_search_result("Invalid query. Enter wallet address, block height, or tx hash.")
    
    async def _search_wallet(self, address: str):
        """Search wallet and show details with clickable transactions."""
        if not self.app.client:
            return
        
        loop = asyncio.get_event_loop()
        
        # Get balance
        balance_result, balance_status = await loop.run_in_executor(
            None,
            lambda: self.app.client.get_wallet_balance(address)
        )
        
        # Get transactions
        tx_result, tx_status = await loop.run_in_executor(
            None,
            lambda: self.app.client.get_wallet_transactions(address, 10, 0)
        )
        
        # Clear and show results
        for child in list(self.search_result_box.children):
            self.search_result_box.remove(child)
        
        result_box = toga.Box(style=Pack(direction=COLUMN, padding=10, background_color="#f5f5f5"))
        
        # Header
        result_box.add(toga.Label(
            f"Wallet: {address}",
            style=Pack(font_weight="bold", padding=(0, 0, 10, 0))
        ))
        
        # Balance
        if balance_status == 200:
            balance = balance_result.get('balance', 0)
            result_box.add(toga.Label(f"Balance: {balance} BZT", style=Pack(padding=3, font_size=14)))
        else:
            result_box.add(toga.Label(f"Balance: Error", style=Pack(padding=3, color="#cc0000")))
        
        # Transactions
        if tx_status == 200:
            txs = tx_result.get('transactions', [])
            result_box.add(toga.Label(
                f"\nRecent Transactions ({len(txs)}):",
                style=Pack(padding=(10, 0, 5, 0), font_weight="bold")
            ))
            
            for tx in txs[:5]:
                tx_type = tx.get('type', 'transfer')
                tx_hash = tx.get('tx_hash', 'unknown')
                
                # Format amount/info based on tx type
                if tx_type == "penalty":
                    amount_info = f"Score: {tx.get('penalty_score', '?')}"
                elif tx_type in ("escrow_release", "dam_verification_reward"):
                    amount_info = f"{tx.get('amount', '?')} BZT"
                elif tx_type == "update_chunk_location":
                    amount_info = f"{len(tx.get('migrated_chunks', []))} chunks"
                else:
                    amount_info = str(tx.get('amount', '0'))
                
                # Friendly type labels
                type_labels = {
                    "escrow_release": "REWARD",
                    "dam_verification_reward": "DAM-RWD",
                    "penalty": "PENALTY",
                    "update_chunk_location": "MIGRATE",
                }
                type_display = type_labels.get(tx_type, tx_type.upper())
                
                tx_row = toga.Box(style=Pack(direction=ROW, padding=3))
                tx_row.add(toga.Label(
                    f"[{type_display}] {self._truncate_hash(tx_hash, 12)} - {amount_info}",
                    style=Pack(flex=1, font_size=11)
                ))
                
                # View button
                view_btn = toga.Button(
                    "View",
                    on_press=lambda w, t=tx: asyncio.create_task(self._show_tx_details(t)),
                    style=Pack(width=50, height=25)
                )
                tx_row.add(view_btn)
                
                result_box.add(tx_row)
        
        self.search_result_box.add(result_box)
    
    async def _search_transaction(self, tx_hash: str):
        """Search transaction by hash."""
        if not self.app.client:
            return
        
        loop = asyncio.get_event_loop()
        result, status = await loop.run_in_executor(
            None,
            lambda: self.app.client.get_transaction(tx_hash)
        )
        
        # Clear and show results
        for child in list(self.search_result_box.children):
            self.search_result_box.remove(child)
        
        if status == 200:
            tx = result.get('transaction', result)
            block_height = tx.get('block_height', 'N/A')
            details = self._format_transaction_details(tx, block_height)
            await self.app.main_window.dialog(
                toga.InfoDialog("Transaction Details", details)
            )
        else:
            self.search_result_box.add(toga.Label(
                f"Transaction not found: {self._truncate_hash(tx_hash, 24)}",
                style=Pack(padding=5, color="#cc0000")
            ))
    
    async def _search_block(self, height: int):
        """Search block by height."""
        await self._show_block_details(str(height))
    
    async def _show_tx_details(self, tx):
        """Show transaction details dialog."""
        block_height = tx.get('block_height', 'N/A')
        details = self._format_transaction_details(tx, block_height)
        await self.app.main_window.dialog(
            toga.InfoDialog("Transaction Details", details)
        )
    
    async def _show_search_result(self, message: str):
        """Show search result message."""
        for child in list(self.search_result_box.children):
            self.search_result_box.remove(child)
        
        self.search_result_box.add(toga.Label(message, style=Pack(padding=5, color="#666666")))
