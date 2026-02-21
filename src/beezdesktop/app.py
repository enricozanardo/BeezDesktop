"""
BeezDesktop Main Application

This is the entry point for the Toga application.
"""

import sys
import os

# Add shared module to path for development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

# Import shared client core
try:
    from shared.client_core import BeezClientCore, ClientState, Wallet
    from shared.client_core.zmq import start_consensus_listener
except ImportError as e:
    print(f"Warning: Could not import shared.client_core: {e}")
    BeezClientCore = None
    ClientState = None


class BeezDesktopApp(toga.App):
    """
    Main Beez Desktop Application.
    
    This application provides a native interface for interacting with
    the Beez Network, including wallet management, file operations,
    and blockchain exploration.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize state and client
        self.state = ClientState() if ClientState else None
        self.client = BeezClientCore(state=self.state) if BeezClientCore else None
        
        # Current view tracking
        self.current_view = "dashboard"
    
    def startup(self):
        """Initialize the application UI."""
        # Create main window
        self.main_window = toga.MainWindow(
            title=self.formal_name,
            size=(1200, 800)
        )
        
        # Create the main content area
        main_box = toga.Box(style=Pack(direction=ROW, flex=1))
        
        # Sidebar navigation
        sidebar = self._create_sidebar()
        main_box.add(sidebar)
        
        # Content area
        self.content_area = toga.Box(
            style=Pack(direction=COLUMN, flex=1, padding=20)
        )
        main_box.add(self.content_area)
        
        # Show dashboard by default
        self._show_dashboard()
        
        self.main_window.content = main_box
        self.main_window.show()
        
        # Start background services
        self._start_background_services()
        
        # Auto-load saved wallet
        self._auto_load_wallet()
    
    def _create_sidebar(self) -> toga.Box:
        """Create the navigation sidebar."""
        sidebar = toga.Box(
            style=Pack(
                direction=COLUMN,
                width=220,
                padding=10,
                background_color="#1a1a2e"
            )
        )
        
        # Logo/Title
        title = toga.Label(
            "BEEZ",
            style=Pack(
                padding=(20, 10),
                font_size=24,
                font_weight="bold",
                color="#f0f0f0"
            )
        )
        sidebar.add(title)
        
        # Navigation buttons
        nav_items = [
            ("Dashboard", "dashboard", self._show_dashboard),
            ("Wallet", "wallet", self._show_wallet),
            ("Files", "files", self._show_files),
            ("Smart", "smart", self._show_smart),
            ("Knowledge", "knowledge", self._show_knowledge),
            ("Transactions", "transactions", self._show_transactions),
            ("Blockchain", "blockchain", self._show_blockchain),
            ("Network", "network", self._show_network),
        ]
        
        for label, view_id, handler in nav_items:
            btn = toga.Button(
                label,
                on_press=handler,
                style=Pack(
                    padding=10,
                    width=200,
                    color="#f0f0f0",       
                    background_color="#16213e"
                )
            )
            sidebar.add(btn)
        
        # Spacer
        sidebar.add(toga.Box(style=Pack(flex=1)))
        
        # Wallet status
        self.wallet_status_label = toga.Label(
            "No wallet connected",
            style=Pack(padding=10, font_size=10, color="#888888")
        )
        sidebar.add(self.wallet_status_label)
        
        return sidebar
    
    def _clear_content(self):
        """Clear the content area and cancel any active view refresh tasks."""
        # Cancel refresh tasks from previous view (e.g. blockchain auto-refresh)
        if hasattr(self, '_active_view') and self._active_view is not None:
            view = self._active_view
            if hasattr(view, '_auto_refresh_enabled'):
                view._auto_refresh_enabled = False
            if hasattr(view, '_refresh_task') and view._refresh_task is not None:
                view._refresh_task.cancel()
                view._refresh_task = None
        self._active_view = None

        for child in list(self.content_area.children):
            self.content_area.remove(child)
    
    def _start_background_services(self):
        """Start background services like consensus listener."""
        if self.state:
            try:
                def on_consensus(data):
                    storage_count = len(self.state.active_nodes)
                    chain_count = len(self.state.chain_nodes)
                    print(f"[CONSENSUS] ✓ {storage_count} storage, {chain_count} chain nodes", flush=True)

                start_consensus_listener(
                    state=self.state,
                    callback=on_consensus,
                )
                print("[APP] Consensus listener started", flush=True)
                
            except Exception as e:
                print(f"[APP] Could not start consensus: {e}", flush=True)
    
    # === View Handlers ===
    
    def _show_dashboard(self, widget=None):
        """Show the dashboard view."""
        self._clear_content()
        self.current_view = "dashboard"
        
        from beezdesktop.views.dashboard import DashboardView
        view = DashboardView(app=self)
        self.content_area.add(view.build())
    
    def _show_wallet(self, widget=None):
        """Show the wallet view."""
        self._clear_content()
        self.current_view = "wallet"
        
        from beezdesktop.views.wallet import WalletView
        view = WalletView(app=self)
        self.content_area.add(view.build())
    
    def _show_files(self, widget=None):
        """Show the files view."""
        self._clear_content()
        self.current_view = "files"
        
        from beezdesktop.views.files import FilesView
        view = FilesView(app=self)
        self.content_area.add(view.build())
    
    def _show_smart(self, widget=None):
        """Show the smart RAG view."""
        self._clear_content()
        self.current_view = "smart"
        
        from beezdesktop.views.smart import SmartView
        view = SmartView(app=self)
        self.content_area.add(view.build())
    
    def _show_knowledge(self, widget=None):
        """Show the knowledge marketplace view."""
        self._clear_content()
        self.current_view = "knowledge"

        from beezdesktop.views.knowledge import KnowledgeView
        view = KnowledgeView(app=self)
        self._active_view = view
        self.content_area.add(view.build())

    def _show_transactions(self, widget=None):
        """Show the transactions view."""
        self._clear_content()
        self.current_view = "transactions"
        
        from beezdesktop.views.transactions import TransactionsView
        view = TransactionsView(app=self)
        self._active_view = view
        self.content_area.add(view.build())
        print("[APP] Transactions view loaded", flush=True)
    
    def _show_blockchain(self, widget=None):
        """Show the blockchain view."""
        self._clear_content()
        self.current_view = "blockchain"
        
        from beezdesktop.views.blockchain import BlockchainView
        view = BlockchainView(app=self)
        self._active_view = view
        self.content_area.add(view.build())
    
    def _show_network(self, widget=None):
        """Show the network view."""
        self._clear_content()
        self.current_view = "network"
        
        from beezdesktop.views.network import NetworkView
        view = NetworkView(app=self)
        self.content_area.add(view.build())
    
    # === Wallet Status ===
    
    def update_wallet_status(self):
        """Update the wallet status display in sidebar."""
        if self.client and self.client.is_wallet_connected():
            wallet = self.client.get_current_wallet()
            addr = wallet.address[:12] + "..." if wallet else ""
            self.wallet_status_label.text = f"Connected: {addr}"
        else:
            self.wallet_status_label.text = "No wallet connected"
    
    def _auto_load_wallet(self):
        """Auto-load saved wallet on startup."""
        try:
            from shared.client_core.wallet_storage import get_wallet_storage
            storage = get_wallet_storage()
            
            if storage.has_saved_wallet() and self.client:
                wallet_data = storage.load_wallet()
                if wallet_data:
                    self.client.connect_wallet(wallet_data['mnemonic'])
                    self.update_wallet_status()
                    print(f"[APP] Auto-loaded wallet: {wallet_data.get('address', '')[:16]}...", flush=True)
        except Exception as e:
            print(f"[APP] Could not auto-load wallet: {e}", flush=True)


def main():
    """Application entry point."""
    return BeezDesktopApp(
        formal_name="Beez Desktop",
        app_id="io.beez.beezdesktop",
        app_name="beezdesktop",
        icon="resources/beezdesktop",
    )


if __name__ == "__main__":
    main().main_loop()
