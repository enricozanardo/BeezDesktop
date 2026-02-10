"""
Transactions View

Transaction management: send BZT, view history.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import asyncio


class TransactionsView:
    """Transaction management view."""
    
    def __init__(self, app):
        self.app = app
        self.recipient_input = None
        self.amount_input = None
        self.history_table = None
    
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
        
        # Transaction history
        history_section = self._build_history_section()
        container.add(history_section)
        
        # Load history
        asyncio.create_task(self._load_transaction_history())
        
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
            "Recipient Address (paste with Ctrl+V):",
            style=Pack(padding=(5, 0, 5, 0))
        )
        section.add(recipient_label)
        
        self.recipient_input = toga.TextInput(
            placeholder="bez... (Ctrl+V to paste)",
            style=Pack(width=450, padding=(0, 0, 10, 0))
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
        
        # Status label
        self.status_label = toga.Label(
            "",
            style=Pack(padding=(10, 0, 0, 0), color="#666666")
        )
        section.add(self.status_label)
        
        return section
    
    def _build_history_section(self) -> toga.Box:
        """Build the transaction history section."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        
        # Header with refresh
        header_row = toga.Box(style=Pack(direction=ROW, padding=(20, 0, 10, 0)))
        
        header = toga.Label(
            "Transaction History",
            style=Pack(font_size=16, font_weight="bold", flex=1)
        )
        header_row.add(header)
        
        refresh_btn = toga.Button(
            "Refresh",
            on_press=lambda w: asyncio.create_task(self._load_transaction_history()),
            style=Pack(width=80)
        )
        header_row.add(refresh_btn)
        
        section.add(header_row)
        
        # Transaction table
        self.history_table = toga.Table(
            headings=["Type", "Amount", "To/From", "Block", "Status"],
            data=[],
            style=Pack(flex=1)
        )
        section.add(self.history_table)
        
        return section
    
    async def _on_send_transaction(self, widget):
        """Handle send transaction button."""
        if not self.app.client:
            return
        
        recipient = self.recipient_input.value.strip()
        amount_str = self.amount_input.value.strip()
        
        # Validation
        if not recipient:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", "Please enter a recipient address.")
            )
            return
        
        if not recipient.startswith("bez"):
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", "Invalid recipient address. Must start with 'bez'.")
            )
            return
        
        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", "Please enter a valid amount.")
            )
            return
        
        # Update status
        self.status_label.text = "Sending transaction..."
        
        # Send transaction asynchronously
        try:
            loop = asyncio.get_event_loop()
            
            # Use the new HTTP API method
            response, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.create_and_send_transaction(amount, recipient)
            )
            
            if status in (200, 201, 202):
                tx_hash = response.get('tx_hash', 'submitted')
                self.status_label.text = f"✓ Sent: {tx_hash[:16]}..."
                await self.app.main_window.dialog(
                    toga.InfoDialog(
                        "Success",
                        f"Transaction sent!\n\n"
                        f"Hash: {tx_hash[:32]}...\n"
                        f"Amount: {amount} BZT\n"
                        f"To: {recipient[:20]}..."
                    )
                )
                # Clear inputs
                self.recipient_input.value = ""
                self.amount_input.value = ""
                # Refresh history
                await self._load_transaction_history()
            else:
                error_msg = response.get('error', response.get('message', 'Unknown error'))
                self.status_label.text = f"✗ Failed: {error_msg}"
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Error", f"Transaction failed: {error_msg}")
                )
                
        except Exception as e:
            self.status_label.text = f"✗ Error: {e}"
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed to send transaction: {e}")
            )
    
    async def _load_transaction_history(self):
        """Load transaction history."""
        if not self.app.client or not self.history_table:
            return
        
        if not self.app.client.is_wallet_connected():
            return
        
        loop = asyncio.get_event_loop()
        
        try:
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.get_wallet_transactions(None, 20, 0, "all")
            )
            
            self.history_table.data.clear()
            
            if status == 200 and result:
                transactions = result.get('transactions', [])
                if transactions is None:
                    transactions = []
                    
                wallet = self.app.client.get_current_wallet()
                my_address = wallet.address if wallet else ""
                
                for tx in transactions:
                    if tx is None:
                        continue
                    tx_type = tx.get('type', 'transfer') or 'transfer'
                    sender = tx.get('sender', '') or ''
                    recipient = tx.get('recipient', '') or ''
                    amount = tx.get('amount', '0') or '0'
                    block_height = tx.get('block_height', '--') or '--'
                    tx_direction = tx.get('direction', '')
                    
                    # Handle ownership transaction display
                    if tx_type in ('ownership_request', 'ownership_accept', 'ownership_reject', 'ownership_cancel'):
                        current_owner = tx.get('current_owner', '') or sender or ''
                        new_owner = tx.get('new_owner', '') or recipient or ''
                        asking_price = tx.get('asking_price', amount) or '0'
                        
                        if tx_type == 'ownership_request':
                            if tx_direction == 'sent':
                                display_type = "↑ Transfer Offer"
                                direction = f"To: {new_owner[:12]}..." if new_owner else "To: --"
                            else:
                                display_type = "↓ Transfer Offer"
                                direction = f"From: {current_owner[:12]}..." if current_owner else "From: --"
                            amount = str(asking_price)
                        elif tx_type == 'ownership_accept':
                            if tx_direction == 'received':
                                display_type = "↓ Asset Sale"
                                direction = f"From: {new_owner[:12]}..." if new_owner else "From: buyer"
                            else:
                                display_type = "↑ Asset Purchase"
                                direction = f"To: {current_owner[:12]}..." if current_owner else "To: seller"
                            amount = str(asking_price)
                        elif tx_type == 'ownership_reject':
                            display_type = "✗ Transfer Rejected"
                            direction = f"File transfer"
                            amount = "0 BZT"
                        elif tx_type == 'ownership_cancel':
                            display_type = "✗ Transfer Cancelled"
                            direction = f"File transfer"
                            amount = "0 BZT"
                    elif tx_type == 'penalty':
                        dam_addr = tx.get('dam_address', '') or ''
                        target_addr = tx.get('target_node_address', '') or ''
                        display_type = "⚠ Penalty"
                        direction = f"DAM: {dam_addr[:12]}... → {target_addr[:12]}..."
                        amount = f"Score: {tx.get('penalty_score', '?')}"
                    elif tx_type == 'escrow_release':
                        escrow_file = tx.get('from_escrow', '') or ''
                        recipient = tx.get('recipient', '') or ''
                        display_type = "↓ Storage Reward"
                        direction = f"Escrow: {escrow_file[:12]}..."
                    elif tx_type == 'dam_verification_reward':
                        escrow_file = tx.get('from_escrow', '') or ''
                        display_type = "↓ DAM Reward"
                        direction = f"Escrow: {escrow_file[:12]}..."
                    elif tx_type == 'update_chunk_location':
                        old_node = tx.get('old_node_id', '') or ''
                        new_node = tx.get('new_node_id', '') or ''
                        display_type = "↔ Chunk Migration"
                        direction = f"{old_node[:8]}... → {new_node[:8]}..."
                        amount = f"{len(tx.get('migrated_chunks', []))} chunks"
                    elif tx_type == 'datrone_reward':
                        display_type = "↓ Datrone Reward"
                        direction = f"To: {recipient[:12]}..." if recipient else "To: --"
                    else:
                        # Standard transaction display
                        if sender == my_address:
                            direction = f"To: {recipient[:12]}..." if recipient else "To: --"
                            display_type = f"↑ {tx_type}"
                        else:
                            direction = f"From: {sender[:12]}..." if sender else "From: --"
                            display_type = f"↓ {tx_type}"
                    
                    self.history_table.data.append([
                        display_type,
                        str(amount),
                        direction,
                        str(block_height),
                        "Confirmed"
                    ])
                    
                if not transactions:
                    self.history_table.data.append([
                        "--", "No transactions yet", "--", "--", "--"
                    ])
            else:
                error = result.get('error', 'Unknown') if result else 'No response'
                print(f"[TX] History error: {error}", flush=True)
                
        except Exception as e:
            print(f"[TX] History exception: {e}", flush=True)
