"""
Transactions View

Transaction management: send BZT, view history.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class TransactionsView:
    """Transaction management view."""
    
    def __init__(self, app):
        self.app = app
        self.recipient_input = None
        self.amount_input = None
    
    def build(self) -> toga.Box:
        """Build the transactions view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Header
        header = toga.Label(
            "Transactions",
            style=Pack(padding=(0, 0, 20, 0), font_size=24, font_weight="bold")
        )
        container.add(header)
        
        # Check if wallet is connected
        if not self.app.client or not self.app.client.is_wallet_connected():
            no_wallet = toga.Label(
                "Please connect a wallet to send transactions.",
                style=Pack(padding=20, color="#888888")
            )
            container.add(no_wallet)
            return container
        
        # Send transaction section
        send_section = self._build_send_section()
        container.add(send_section)
        
        # Transaction history (placeholder)
        history_section = self._build_history_section()
        container.add(history_section)
        
        return container
    
    def _build_send_section(self) -> toga.Box:
        """Build the send transaction section."""
        section = toga.Box(
            style=Pack(direction=COLUMN, padding=10, background_color="#f5f5f5")
        )
        
        header = toga.Label(
            "Send BZT",
            style=Pack(font_size=16, font_weight="bold", padding=(0, 0, 10, 0))
        )
        section.add(header)
        
        # Recipient input
        recipient_label = toga.Label(
            "Recipient Address:",
            style=Pack(padding=(5, 0, 5, 0))
        )
        section.add(recipient_label)
        
        self.recipient_input = toga.TextInput(
            placeholder="bez...",
            style=Pack(width=400, padding=(0, 0, 10, 0))
        )
        section.add(self.recipient_input)
        
        # Amount input
        amount_label = toga.Label(
            "Amount (BZT):",
            style=Pack(padding=(5, 0, 5, 0))
        )
        section.add(amount_label)
        
        self.amount_input = toga.TextInput(
            placeholder="0.00",
            style=Pack(width=150, padding=(0, 0, 10, 0))
        )
        section.add(self.amount_input)
        
        # Send button
        send_btn = toga.Button(
            "Send Transaction",
            on_press=self._on_send_transaction,
            style=Pack(width=200, padding=(10, 0, 0, 0))
        )
        section.add(send_btn)
        
        return section
    
    def _build_history_section(self) -> toga.Box:
        """Build the transaction history section."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        
        header = toga.Label(
            "Transaction History",
            style=Pack(font_size=16, font_weight="bold", padding=(20, 0, 10, 0))
        )
        section.add(header)
        
        # Placeholder for transaction list
        placeholder = toga.Label(
            "Transaction history will appear here.",
            style=Pack(padding=20, color="#888888")
        )
        section.add(placeholder)
        
        return section
    
    def _on_send_transaction(self, widget):
        """Handle send transaction button."""
        if not self.app.client:
            return
        
        recipient = self.recipient_input.value.strip()
        amount_str = self.amount_input.value.strip()
        
        # Validation
        if not recipient:
            self.app.main_window.error_dialog(
                "Error",
                "Please enter a recipient address."
            )
            return
        
        if not recipient.startswith("bez"):
            self.app.main_window.error_dialog(
                "Error",
                "Invalid recipient address. Must start with 'bez'."
            )
            return
        
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            self.app.main_window.error_dialog(
                "Error",
                "Please enter a valid amount."
            )
            return
        
        # Create and send transaction
        try:
            tx = self.app.client.create_transaction(amount, recipient)
            response, status = self.app.client.send_transaction(tx)
            
            if status == 200:
                self.app.main_window.info_dialog(
                    "Success",
                    f"Transaction sent!\nHash: {tx.tx_hash[:16]}..."
                )
                # Clear inputs
                self.recipient_input.value = ""
                self.amount_input.value = ""
            else:
                self.app.main_window.error_dialog(
                    "Error",
                    f"Transaction failed: {response.get('error', 'Unknown error')}"
                )
                
        except Exception as e:
            self.app.main_window.error_dialog(
                "Error",
                f"Failed to send transaction: {e}"
            )
