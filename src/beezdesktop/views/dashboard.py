"""
Dashboard View

Provides quick overview and common actions.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class DashboardView:
    """Dashboard view with quick actions and overview."""
    
    def __init__(self, app):
        self.app = app
    
    def build(self) -> toga.Box:
        """Build the dashboard view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Header
        header = toga.Label(
            "Dashboard",
            style=Pack(padding=(0, 0, 20, 0), font_size=24, font_weight="bold")
        )
        container.add(header)
        
        # Quick actions row
        actions_box = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 20, 0)))
        
        # Wallet action card
        wallet_card = self._create_action_card(
            "Wallet",
            "Connect or create a wallet",
            self._on_wallet_click
        )
        actions_box.add(wallet_card)
        
        # Upload action card
        upload_card = self._create_action_card(
            "Upload File",
            "Upload a file to the network",
            self._on_upload_click
        )
        actions_box.add(upload_card)
        
        # Send action card
        send_card = self._create_action_card(
            "Send BZT",
            "Send tokens to another wallet",
            self._on_send_click
        )
        actions_box.add(send_card)
        
        container.add(actions_box)
        
        # Status section
        status_header = toga.Label(
            "Network Status",
            style=Pack(padding=(20, 0, 10, 0), font_size=18, font_weight="bold")
        )
        container.add(status_header)
        
        # Status info
        status_box = self._create_status_section()
        container.add(status_box)
        
        return container
    
    def _create_action_card(self, title: str, description: str, handler) -> toga.Box:
        """Create an action card widget."""
        card = toga.Box(
            style=Pack(
                direction=COLUMN,
                padding=15,
                width=200,
                background_color="#f5f5f5"
            )
        )
        
        title_label = toga.Label(
            title,
            style=Pack(font_size=16, font_weight="bold", padding=(0, 0, 5, 0))
        )
        card.add(title_label)
        
        desc_label = toga.Label(
            description,
            style=Pack(font_size=12, color="#666666", padding=(0, 0, 10, 0))
        )
        card.add(desc_label)
        
        btn = toga.Button(
            "Open",
            on_press=handler,
            style=Pack(width=170)
        )
        card.add(btn)
        
        return card
    
    def _create_status_section(self) -> toga.Box:
        """Create the network status section."""
        status_box = toga.Box(
            style=Pack(direction=COLUMN, padding=10, background_color="#f9f9f9")
        )
        
        # Get node counts from state
        storage_count = len(self.app.state.active_nodes) if self.app.state else 0
        chain_count = len(self.app.state.chain_nodes) if self.app.state else 0
        dam_count = len(self.app.state.manager_nodes) if self.app.state else 0
        
        status_items = [
            f"Storage Nodes: {storage_count}",
            f"Chain Nodes: {chain_count}",
            f"DAM Nodes: {dam_count}",
        ]
        
        for item in status_items:
            label = toga.Label(item, style=Pack(padding=5))
            status_box.add(label)
        
        return status_box
    
    def _on_wallet_click(self, widget):
        """Navigate to wallet view."""
        self.app._show_wallet()
    
    def _on_upload_click(self, widget):
        """Navigate to files view."""
        self.app._show_files()
    
    def _on_send_click(self, widget):
        """Navigate to transactions view."""
        self.app._show_transactions()
