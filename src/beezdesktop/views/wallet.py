"""
Wallet View

Wallet management: create, connect, disconnect, view balance.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class WalletView:
    """Wallet management view."""
    
    def __init__(self, app):
        self.app = app
        self.mnemonic_input = None
        self.balance_label = None
        self.address_label = None
    
    def build(self) -> toga.Box:
        """Build the wallet view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Header
        header = toga.Label(
            "Wallet",
            style=Pack(padding=(0, 0, 20, 0), font_size=24, font_weight="bold")
        )
        container.add(header)
        
        # Check if wallet is connected
        if self.app.client and self.app.client.is_wallet_connected():
            container.add(self._build_connected_view())
        else:
            container.add(self._build_disconnected_view())
        
        return container
    
    def _build_disconnected_view(self) -> toga.Box:
        """Build view when no wallet is connected."""
        box = toga.Box(style=Pack(direction=COLUMN, padding=10))
        
        # Create new wallet section
        create_header = toga.Label(
            "Create New Wallet",
            style=Pack(font_size=16, font_weight="bold", padding=(0, 0, 10, 0))
        )
        box.add(create_header)
        
        create_btn = toga.Button(
            "Generate New Wallet",
            on_press=self._on_create_wallet,
            style=Pack(width=200, padding=(0, 0, 20, 0))
        )
        box.add(create_btn)
        
        # Connect existing wallet section
        connect_header = toga.Label(
            "Connect Existing Wallet",
            style=Pack(font_size=16, font_weight="bold", padding=(20, 0, 10, 0))
        )
        box.add(connect_header)
        
        mnemonic_label = toga.Label(
            "Enter your 12-word mnemonic phrase:",
            style=Pack(padding=(0, 0, 5, 0))
        )
        box.add(mnemonic_label)
        
        self.mnemonic_input = toga.MultilineTextInput(
            placeholder="word1 word2 word3 ...",
            style=Pack(width=400, height=80, padding=(0, 0, 10, 0))
        )
        box.add(self.mnemonic_input)
        
        connect_btn = toga.Button(
            "Connect Wallet",
            on_press=self._on_connect_wallet,
            style=Pack(width=200)
        )
        box.add(connect_btn)
        
        return box
    
    def _build_connected_view(self) -> toga.Box:
        """Build view when wallet is connected."""
        box = toga.Box(style=Pack(direction=COLUMN, padding=10))
        
        wallet = self.app.client.get_current_wallet()
        
        # Wallet info
        info_header = toga.Label(
            "Connected Wallet",
            style=Pack(font_size=16, font_weight="bold", padding=(0, 0, 10, 0))
        )
        box.add(info_header)
        
        # Address
        address_row = toga.Box(style=Pack(direction=ROW, padding=5))
        address_label = toga.Label("Address: ", style=Pack(font_weight="bold"))
        address_row.add(address_label)
        self.address_label = toga.Label(wallet.address if wallet else "")
        address_row.add(self.address_label)
        box.add(address_row)
        
        # Balance
        balance_row = toga.Box(style=Pack(direction=ROW, padding=5))
        balance_label = toga.Label("Balance: ", style=Pack(font_weight="bold"))
        balance_row.add(balance_label)
        self.balance_label = toga.Label("Loading...")
        balance_row.add(self.balance_label)
        box.add(balance_row)
        
        # Refresh balance button
        refresh_btn = toga.Button(
            "Refresh Balance",
            on_press=self._on_refresh_balance,
            style=Pack(width=150, padding=(10, 0, 0, 0))
        )
        box.add(refresh_btn)
        
        # Disconnect button
        disconnect_btn = toga.Button(
            "Disconnect Wallet",
            on_press=self._on_disconnect_wallet,
            style=Pack(width=150, padding=(20, 0, 0, 0))
        )
        box.add(disconnect_btn)
        
        # Auto-refresh balance
        self._refresh_balance()
        
        return box
    
    def _on_create_wallet(self, widget):
        """Handle create wallet button."""
        if not self.app.client:
            return
        
        result = self.app.client.create_wallet()
        
        # Show mnemonic in a dialog
        self.app.main_window.info_dialog(
            "Wallet Created",
            f"Address: {result['address']}\n\n"
            f"IMPORTANT: Save your mnemonic phrase:\n\n"
            f"{result['mnemonic']}\n\n"
            "This is the ONLY way to recover your wallet!"
        )
        
        self.app.update_wallet_status()
        self.app._show_wallet()  # Refresh view
    
    def _on_connect_wallet(self, widget):
        """Handle connect wallet button."""
        if not self.app.client or not self.mnemonic_input:
            return
        
        mnemonic = self.mnemonic_input.value.strip()
        
        if not mnemonic:
            self.app.main_window.error_dialog(
                "Error",
                "Please enter your mnemonic phrase."
            )
            return
        
        # Validate mnemonic (basic check)
        words = mnemonic.split()
        if len(words) not in [12, 24]:
            self.app.main_window.error_dialog(
                "Error",
                "Mnemonic must be 12 or 24 words."
            )
            return
        
        try:
            result = self.app.client.connect_wallet(mnemonic)
            self.app.main_window.info_dialog(
                "Success",
                f"Wallet connected!\nAddress: {result['address']}"
            )
            self.app.update_wallet_status()
            self.app._show_wallet()  # Refresh view
        except Exception as e:
            self.app.main_window.error_dialog(
                "Error",
                f"Failed to connect wallet: {e}"
            )
    
    def _on_disconnect_wallet(self, widget):
        """Handle disconnect wallet button."""
        if not self.app.client:
            return
        
        self.app.client.disconnect_wallet()
        self.app.update_wallet_status()
        self.app._show_wallet()  # Refresh view
    
    def _on_refresh_balance(self, widget):
        """Handle refresh balance button."""
        self._refresh_balance()
    
    def _refresh_balance(self):
        """Refresh the wallet balance."""
        if not self.app.client or not self.balance_label:
            return
        
        result, status = self.app.client.get_wallet_balance()
        
        if status == 200:
            self.balance_label.text = f"{result.get('balance', 0)} BZT"
        else:
            self.balance_label.text = "Unable to fetch balance"
