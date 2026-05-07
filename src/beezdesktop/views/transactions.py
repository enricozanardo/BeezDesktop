"""
Transactions View

Transaction management: send BZT, view history.
Uses SearchableTable and LoadingIndicator for better UX.
"""

import logging
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import asyncio

from beezdesktop.theme import (
    Colors, Font, Spacing,
    page_header, card, spacer,
    primary_button, secondary_button,
    SearchableTable, LoadingIndicator,
)
from beezdesktop.views.lifecycle import ViewLifecycle

logger = logging.getLogger("beezdesktop.transactions")


class TransactionsView(ViewLifecycle):
    """Transaction management view."""

    def __init__(self, app):
        ViewLifecycle.__init__(self, app)
        self.recipient_input = None
        self.amount_input = None
        self._history_table = None
        self._loading = None

    def build(self) -> toga.Box:
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        container.add(page_header("Transactions", "Send tokens and view transaction history"))

        wallet_ok = self.app.client and self.app.client.is_wallet_connected()
        if not wallet_ok:
            container.add(toga.Label(
                "Please connect a wallet to send transactions.",
                style=Pack(padding=Spacing.XL, color=Colors.TEXT_MUTED, font_size=Font.SIZE_BODY),
            ))
            return container

        container.add(self._send_section())
        container.add(spacer(Spacing.SECTION_GAP))
        container.add(self._history_section())

        # B-17: load history via thread (bg_load), not asyncio task.
        # gbulb has been observed to leave create_task'd coroutines
        # PENDING after a heavy GTK event burst (file upload), which
        # left the history table empty even though the loop was alive
        # enough to dispatch ``call_soon_threadsafe`` callbacks.
        self._kick_history_load()
        return container

    def _send_section(self) -> toga.Box:
        section = card(title="Send BZT", bg=Colors.BG_CARD)

        section.add(toga.Label(
            "Recipient Address",
            style=Pack(font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY, padding=(0, 0, Spacing.XS, 0)),
        ))
        self.recipient_input = toga.TextInput(
            placeholder="bez...",
            style=Pack(flex=1, padding=(0, 0, Spacing.MD, 0)),
        )
        section.add(self.recipient_input)

        section.add(toga.Label(
            "Amount (BZT)",
            style=Pack(font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY, padding=(0, 0, Spacing.XS, 0)),
        ))
        self.amount_input = toga.TextInput(
            placeholder="0.00",
            style=Pack(width=160, padding=(0, 0, Spacing.MD, 0)),
        )
        section.add(self.amount_input)

        btn_row = toga.Box(style=Pack(direction=ROW, alignment="center"))
        btn_row.add(primary_button("Send Transaction", self.wrap_handler(self._on_send, "send")))
        self.status_label = toga.Label(
            "",
            style=Pack(padding=(0, 0, 0, Spacing.MD), font_size=Font.SIZE_SMALL, color=Colors.TEXT_SECONDARY),
        )
        btn_row.add(self.status_label)
        section.add(btn_row)

        return section

    def _history_section(self) -> toga.Box:
        section = toga.Box(style=Pack(direction=COLUMN, flex=1))

        header_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, Spacing.SM, 0), alignment="center"))
        header_row.add(toga.Label(
            "Transaction History",
            style=Pack(font_size=Font.SIZE_H2, font_weight="bold", color=Colors.TEXT_PRIMARY, flex=1),
        ))
        header_row.add(secondary_button(
            "Refresh",
            lambda w: self._kick_history_load(),
            width=100,
        ))
        section.add(header_row)

        # Loading indicator
        self._loading = LoadingIndicator("Loading transactions...")
        section.add(self._loading.box)

        # Searchable table
        self._history_table = SearchableTable(
            headings=["Type", "Amount", "To/From", "Block", "Status"],
            page_size=15,
            search_placeholder="Search transactions...",
        )
        section.add(self._history_table.box)

        return section

    # ------------------------------------------------------------------ #
    # HANDLERS
    # ------------------------------------------------------------------ #

    async def _on_send(self, widget):
        if not self.app.client:
            return

        recipient = self.recipient_input.value.strip()
        amount_str = self.amount_input.value.strip()

        if not recipient:
            await self.app.main_window.dialog(toga.ErrorDialog("Error", "Please enter a recipient address."))
            return
        if not recipient.startswith("bez"):
            await self.app.main_window.dialog(toga.ErrorDialog("Error", "Invalid address. Must start with 'bez'."))
            return

        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            await self.app.main_window.dialog(toga.ErrorDialog("Error", "Please enter a valid amount."))
            return

        self.status_label.text = "Sending..."

        try:
            loop = asyncio.get_event_loop()
            response, status = await loop.run_in_executor(
                None, lambda: self.app.client.create_and_send_transaction(amount, recipient)
            )
            if self._destroyed:
                return
            if status in (200, 201, 202):
                tx_hash = response.get('tx_hash', 'submitted')
                self.status_label.text = f"\u2713 Sent: {tx_hash[:16]}..."
                await self.app.main_window.dialog(toga.InfoDialog(
                    "Success",
                    f"Transaction sent!\n\nHash: {tx_hash[:32]}...\nAmount: {amount} BZT\nTo: {recipient[:20]}...",
                ))
                self.recipient_input.value = ""
                self.amount_input.value = ""
                await self._load_history()
            else:
                err = response.get('error', response.get('message', 'Unknown error'))
                self.status_label.text = f"\u2717 Failed: {err}"
                await self.app.main_window.dialog(toga.ErrorDialog("Error", f"Transaction failed: {err}"))
        except Exception as e:
            self.status_label.text = f"\u2717 Error: {e}"
            await self.app.main_window.dialog(toga.ErrorDialog("Error", f"Failed: {e}"))

    def _kick_history_load(self) -> None:
        """B-17 safe history loader. Runs the chain fetch in a thread.

        We deliberately do NOT use ``spawn_task`` + ``run_in_executor``
        because we have observed that pattern silently stop firing on
        gbulb after a file upload burst.
        """
        if not self.app.client or not self._history_table:
            return
        if not self.app.client.is_wallet_connected():
            return

        try:
            self._loading.show("Loading transactions...")
        except Exception:
            pass

        def fetch():
            return self.app.client.get_wallet_transactions(None, 50, 0, "all")

        self.bg_load(
            work_fn=fetch,
            ui_fn=self._on_history_loaded,
            error_ui_fn=self._on_history_error,
            name="load_history",
        )

    def _on_history_loaded(self, result_status: tuple) -> None:
        try:
            result, status = result_status
            rows = []
            if status == 200 and result:
                transactions = result.get('transactions', []) or []
                wallet = self.app.client.get_current_wallet()
                my_address = wallet.address if wallet else ""

                for tx in transactions:
                    if tx is None:
                        continue
                    rows.append(self._format_tx_row(tx, my_address))

            self._history_table.set_data(rows)
        except Exception as e:
            logger.info(f"[TX] History display exception: {e}")
        finally:
            try:
                self._loading.hide()
            except Exception:
                pass

    def _on_history_error(self, exc: Exception) -> None:
        logger.info(f"[TX] History fetch exception: {exc}")
        try:
            self._loading.hide()
        except Exception:
            pass

    async def _load_history(self):
        """Legacy async loader - routes through bg_load for B-17 safety."""
        self._kick_history_load()

    def _format_tx_row(self, tx: dict, my_address: str) -> tuple:
        tx_type = tx.get('type', 'transfer') or 'transfer'
        sender = tx.get('sender', '') or ''
        recipient = tx.get('recipient', '') or ''
        amount = tx.get('amount', '0') or '0'
        block_height = tx.get('block_height', '--') or '--'
        tx_direction = tx.get('direction', '')

        if tx_type in ('ownership_request', 'ownership_accept', 'ownership_reject', 'ownership_cancel'):
            current_owner = tx.get('current_owner', '') or sender or ''
            new_owner = tx.get('new_owner', '') or recipient or ''
            asking_price = tx.get('asking_price', amount) or '0'

            if tx_type == 'ownership_request':
                if tx_direction == 'sent':
                    display_type, direction = "\u2191 Transfer Offer", f"To: {new_owner[:12]}..." if new_owner else "To: --"
                else:
                    display_type, direction = "\u2193 Transfer Offer", f"From: {current_owner[:12]}..." if current_owner else "From: --"
                amount = str(asking_price)
            elif tx_type == 'ownership_accept':
                if tx_direction == 'received':
                    display_type, direction = "\u2193 Asset Sale", f"From: {new_owner[:12]}..." if new_owner else "From: buyer"
                else:
                    display_type, direction = "\u2191 Asset Purchase", f"To: {current_owner[:12]}..." if current_owner else "To: seller"
                amount = str(asking_price)
            elif tx_type == 'ownership_reject':
                display_type, direction, amount = "\u2717 Transfer Rejected", "File transfer", "0"
            else:
                display_type, direction, amount = "\u2717 Transfer Cancelled", "File transfer", "0"
        elif tx_type == 'penalty':
            dam_addr = tx.get('dam_address', '') or ''
            target = tx.get('target_node_address', '') or ''
            display_type = "\u26A0 Penalty"
            direction = f"DAM: {dam_addr[:12]}..."
            amount = f"Score: {tx.get('penalty_score', '?')}"
        elif tx_type == 'escrow_release':
            display_type, direction = "\u2193 Storage Reward", f"Escrow: {(tx.get('from_escrow', '') or '')[:12]}..."
        elif tx_type == 'dam_verification_reward':
            display_type, direction = "\u2193 DAM Reward", f"Escrow: {(tx.get('from_escrow', '') or '')[:12]}..."
        elif tx_type == 'update_chunk_location':
            old_n = tx.get('old_node_id', '') or ''
            new_n = tx.get('new_node_id', '') or ''
            display_type = "\u21C4 Chunk Migration"
            direction = f"{old_n[:8]}... \u2192 {new_n[:8]}..."
            amount = f"{len(tx.get('migrated_chunks', []))} chunks"
        elif tx_type == 'datrone_reward':
            display_type = "\u2193 Datrone Reward"
            direction = f"To: {recipient[:12]}..." if recipient else "To: --"
        elif tx_type in ('smart_index', 'smart_query', 'knowledge_publish', 'knowledge_query', 'knowledge_purchase'):
            display_type = f"\u21C4 {tx_type.replace('_', ' ').title()}"
            direction = f"To: {recipient[:12]}..." if recipient else f"From: {sender[:12]}..."
            amount = str(tx.get('total_cost', tx.get('cost', tx.get('amount', '0'))))
        else:
            if sender == my_address:
                direction = f"To: {recipient[:12]}..." if recipient else "To: --"
                display_type = f"\u2191 {tx_type}"
            else:
                direction = f"From: {sender[:12]}..." if sender else "From: --"
                display_type = f"\u2193 {tx_type}"

        return (display_type, str(amount), direction, str(block_height), "Confirmed")
