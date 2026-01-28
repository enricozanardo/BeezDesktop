"""
Blockchain View

Blockchain explorer: view blocks, transactions, wallet lookup.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class BlockchainView:
    """Blockchain explorer view."""
    
    def __init__(self, app):
        self.app = app
        self.search_input = None
    
    def build(self) -> toga.Box:
        """Build the blockchain view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Header
        header = toga.Label(
            "Blockchain Explorer",
            style=Pack(padding=(0, 0, 20, 0), font_size=24, font_weight="bold")
        )
        container.add(header)
        
        # Search section
        search_section = self._build_search_section()
        container.add(search_section)
        
        # Info section
        info_section = self._build_info_section()
        container.add(info_section)
        
        return container
    
    def _build_search_section(self) -> toga.Box:
        """Build the search section."""
        section = toga.Box(
            style=Pack(direction=COLUMN, padding=10, background_color="#f5f5f5")
        )
        
        header = toga.Label(
            "Search",
            style=Pack(font_size=16, font_weight="bold", padding=(0, 0, 10, 0))
        )
        section.add(header)
        
        # Search row
        search_row = toga.Box(style=Pack(direction=ROW, padding=5))
        
        self.search_input = toga.TextInput(
            placeholder="Enter transaction hash, block height, or wallet address...",
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
        
        return section
    
    def _build_info_section(self) -> toga.Box:
        """Build the blockchain info section."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        
        header = toga.Label(
            "Blockchain Info",
            style=Pack(font_size=16, font_weight="bold", padding=(20, 0, 10, 0))
        )
        section.add(header)
        
        # Placeholder info
        info_items = [
            "Latest Block: Loading...",
            "Total Blocks: Loading...",
            "Consensus: Loading...",
        ]
        
        for item in info_items:
            label = toga.Label(item, style=Pack(padding=5))
            section.add(label)
        
        return section
    
    def _on_search(self, widget):
        """Handle search button."""
        query = self.search_input.value.strip()
        
        if not query:
            return
        
        # Determine search type and execute
        if query.startswith("bez"):
            # Wallet address
            self.app.main_window.info_dialog(
                "Wallet Search",
                f"Searching for wallet: {query[:20]}...\n"
                "Wallet lookup will be implemented."
            )
        elif query.startswith("0x") or len(query) == 64:
            # Transaction hash
            self.app.main_window.info_dialog(
                "Transaction Search",
                f"Searching for transaction: {query[:20]}...\n"
                "Transaction lookup will be implemented."
            )
        else:
            # Block height
            try:
                block_height = int(query)
                self.app.main_window.info_dialog(
                    "Block Search",
                    f"Searching for block #{block_height}\n"
                    "Block lookup will be implemented."
                )
            except ValueError:
                self.app.main_window.error_dialog(
                    "Invalid Query",
                    "Please enter a valid wallet address, transaction hash, or block number."
                )
