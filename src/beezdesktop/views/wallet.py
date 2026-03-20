"""
Wallet View

Wallet management: create, connect, import/export, view balance.
Redesigned with card-based layout and consistent theming.
"""

import logging
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import asyncio
import os
from pathlib import Path

from beezdesktop.theme import (
    Colors, Font, Spacing,
    page_header, card, info_row, spacer,
    primary_button, secondary_button, danger_button,
    status_badge,
)

logger = logging.getLogger("beezdesktop.wallet")


def _safe_async(handler, name="unnamed"):
    """Wrap an async handler for Toga button press."""
    def wrapper(widget):
        async def _inner():
            try:
                await handler(widget)
            except Exception as e:
                logger.error("[WALLET] Handler '%s' error: %s", name, e)
                import traceback
                traceback.print_exc()
        asyncio.create_task(_inner())
    return wrapper


class WalletView:
    """Wallet management view."""

    def __init__(self, app):
        self.app = app
        self.mnemonic_input = None
        self.balance_label = None
        self._wallet_storage = None

    def _get_storage(self):
        if self._wallet_storage is None:
            try:
                from shared.client_core.wallet_storage import get_wallet_storage
                self._wallet_storage = get_wallet_storage()
            except ImportError:
                pass
        return self._wallet_storage

    # ------------------------------------------------------------------ #
    # BUILD
    # ------------------------------------------------------------------ #

    def build(self) -> toga.Box:
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        container.add(page_header("Wallet", "Manage your Beez wallet"))

        if self.app.client and self.app.client.is_wallet_connected():
            container.add(self._connected_section())
        else:
            container.add(self._disconnected_section())

        return container

    # ------------------------------------------------------------------ #
    # DISCONNECTED
    # ------------------------------------------------------------------ #

    def _disconnected_section(self) -> toga.Box:
        box = toga.Box(style=Pack(direction=COLUMN))

        # Saved wallet
        storage = self._get_storage()
        if storage and storage.has_saved_wallet():
            saved = card(title="Saved Wallet Found", bg=Colors.SURFACE_SUCCESS)
            saved.add(toga.Label(
                "A previously saved wallet was found on this device.",
                style=Pack(font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY, padding=(0, 0, Spacing.MD, 0)),
            ))
            btn_row = toga.Box(style=Pack(direction=ROW))
            btn_row.add(primary_button("Load Saved Wallet", _safe_async(self._load_saved, "load")))
            btn_row.add(toga.Box(style=Pack(width=Spacing.SM)))
            btn_row.add(danger_button("Delete Saved", _safe_async(self._delete_saved, "delete"), width=140))
            saved.add(btn_row)
            box.add(saved)
            box.add(spacer(Spacing.SECTION_GAP))

        # Create new
        create = card(title="Create New Wallet", bg=Colors.BG_CARD)
        create.add(toga.Label(
            "Generate a brand-new wallet with a 12-word mnemonic phrase.",
            style=Pack(font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY, padding=(0, 0, Spacing.MD, 0)),
        ))
        create.add(primary_button("Generate Wallet", _safe_async(self._create_wallet, "create")))
        box.add(create)
        box.add(spacer(Spacing.MD))

        # Import from file
        import_card = card(title="Import from File", bg=Colors.BG_CARD)
        import_card.add(toga.Label(
            "Restore a wallet from a previously exported backup file.",
            style=Pack(font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY, padding=(0, 0, Spacing.MD, 0)),
        ))
        import_card.add(secondary_button("Import Wallet File", _safe_async(self._import_file, "import")))
        box.add(import_card)
        box.add(spacer(Spacing.MD))

        # Connect with mnemonic
        connect = card(title="Connect with Mnemonic", bg=Colors.BG_CARD)
        connect.add(toga.Label(
            "Enter your 12-word mnemonic phrase to connect an existing wallet.",
            style=Pack(font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY, padding=(0, 0, Spacing.SM, 0)),
        ))
        self.mnemonic_input = toga.MultilineTextInput(
            placeholder="word1 word2 word3 ... word12",
            style=Pack(height=80, padding=(0, 0, Spacing.MD, 0)),
        )
        connect.add(self.mnemonic_input)
        connect.add(primary_button("Connect Wallet", _safe_async(self._connect_mnemonic, "connect")))
        box.add(connect)

        return box

    # ------------------------------------------------------------------ #
    # CONNECTED
    # ------------------------------------------------------------------ #

    def _connected_section(self) -> toga.Box:
        wallet = self.app.client.get_current_wallet()
        box = toga.Box(style=Pack(direction=COLUMN))

        # Wallet info card
        info = card(title="Connected Wallet", bg=Colors.SURFACE_INFO)
        info.add(info_row("Address", wallet.address if wallet else "", label_width=80))

        # Balance
        balance_row = toga.Box(style=Pack(direction=ROW, padding=(Spacing.SM, 0), alignment="center"))
        balance_row.add(toga.Label("Balance", style=Pack(width=80, font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY)))
        self.balance_label = toga.Label("Loading...", style=Pack(font_size=Font.SIZE_H2, font_weight="bold", color=Colors.PRIMARY))
        balance_row.add(self.balance_label)
        info.add(balance_row)

        box.add(info)
        box.add(spacer(Spacing.MD))

        # Actions card
        actions = card(title="Actions", bg=Colors.BG_CARD)
        btn_row = toga.Box(style=Pack(direction=ROW))
        btn_row.add(primary_button("Refresh Balance", self._refresh_balance))
        btn_row.add(toga.Box(style=Pack(width=Spacing.SM)))
        btn_row.add(secondary_button("Export Wallet", _safe_async(self._export, "export")))
        actions.add(btn_row)

        # Save status
        storage = self._get_storage()
        if storage:
            is_saved = storage.has_saved_wallet()
            if is_saved:
                actions.add(spacer(Spacing.SM))
                actions.add(status_badge("Wallet saved for auto-load", online=True))
            else:
                actions.add(spacer(Spacing.SM))
                save_row = toga.Box(style=Pack(direction=ROW, alignment="center"))
                save_row.add(toga.Label(
                    "Wallet not saved for auto-load",
                    style=Pack(font_size=Font.SIZE_SMALL, color=Colors.TEXT_MUTED, padding=(0, Spacing.SM, 0, 0)),
                ))
                save_row.add(secondary_button("Save for Auto-load", _safe_async(self._save_wallet, "save"), width=160))
                actions.add(save_row)

        box.add(actions)
        box.add(spacer(Spacing.MD))

        # Disconnect
        box.add(danger_button("Disconnect Wallet", _safe_async(self._disconnect, "disconnect"), width=180))

        # Trigger async balance load
        asyncio.create_task(self._load_balance())

        return box

    # ------------------------------------------------------------------ #
    # HANDLERS
    # ------------------------------------------------------------------ #

    async def _create_wallet(self, widget):
        if not self.app.client:
            return
        result = self.app.client.create_wallet()
        await self._show_export_dialog(result['address'], result['mnemonic'], is_new=True)
        self.app.update_wallet_status()
        self.app._show_wallet()

    async def _show_export_dialog(self, address, mnemonic, is_new=False):
        title = "New Wallet Created!" if is_new else "Export Wallet"
        msg = (
            f"Address: {address}\n\n"
            "Would you like to export your wallet backup file?\n"
            "This is the only way to recover your wallet later."
        )
        if await self.app.main_window.dialog(toga.QuestionDialog(title, msg)):
            await self._save_to_file(address, mnemonic)
        else:
            await self.app.main_window.dialog(toga.InfoDialog(
                "Wallet Mnemonic",
                f"Address: {address}\n\nMnemonic:\n{mnemonic}\n\nWrite this down and keep it safe!",
            ))

    async def _save_to_file(self, address, mnemonic):
        try:
            path = await self.app.main_window.dialog(toga.SaveFileDialog(
                title="Save Wallet Backup",
                suggested_filename=f"beez_wallet_{address[:8]}.txt",
                file_types=["txt"],
            ))
            if path:
                storage = self._get_storage()
                if storage:
                    storage.export_wallet(str(path), mnemonic, address)
                else:
                    with open(str(path), 'w') as f:
                        f.write(f"=== BEEZ WALLET BACKUP ===\nAddress: {address}\n\nMnemonic:\n{mnemonic}\n\n=== KEEP SECURE ===\n")
                await self.app.main_window.dialog(toga.InfoDialog("Saved", f"Wallet exported to:\n{path}"))
        except Exception as e:
            await self.app.main_window.dialog(toga.ErrorDialog("Error", f"Export failed: {e}"))

    async def _export(self, widget):
        wallet = self.app.client.get_current_wallet()
        if wallet:
            await self._save_to_file(wallet.address, wallet.mnemonic)

    async def _connect_mnemonic(self, widget):
        if not self.app.client or not self.mnemonic_input:
            return
        mnemonic = self.mnemonic_input.value.strip()
        if not mnemonic:
            await self.app.main_window.dialog(toga.ErrorDialog("Error", "Please enter your mnemonic phrase."))
            return
        words = mnemonic.split()
        if len(words) not in [12, 24]:
            await self.app.main_window.dialog(toga.ErrorDialog("Error", f"Expected 12 or 24 words, got {len(words)}."))
            return
        try:
            result = self.app.client.connect_wallet(mnemonic)
            await self.app.main_window.dialog(toga.InfoDialog("Connected", f"Wallet: {result['address']}"))
            self.app.update_wallet_status()
            self.app._show_wallet()
        except Exception as e:
            await self.app.main_window.dialog(toga.ErrorDialog("Error", f"Connection failed: {e}"))

    async def _import_file(self, widget):
        try:
            path = await self.app.main_window.dialog(toga.OpenFileDialog(
                title="Import Wallet Backup", file_types=["txt"], multiple_select=False,
            ))
            if path:
                with open(str(path)) as f:
                    content = f.read()
                mnemonic = self._extract_mnemonic(content)
                if mnemonic:
                    result = self.app.client.connect_wallet(mnemonic)
                    await self.app.main_window.dialog(toga.InfoDialog("Imported", f"Wallet: {result['address']}"))
                    self.app.update_wallet_status()
                    self.app._show_wallet()
                else:
                    await self.app.main_window.dialog(toga.ErrorDialog("Error", "Could not find mnemonic in file."))
        except Exception as e:
            await self.app.main_window.dialog(toga.ErrorDialog("Error", f"Import failed: {e}"))

    def _extract_mnemonic(self, content: str) -> str:
        lines = content.strip().split('\n')
        for i, line in enumerate(lines):
            if 'mnemonic' in line.lower() and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if len(candidate.split()) in [12, 24]:
                    return candidate
            words = line.strip().split()
            if len(words) in [12, 24] and not line.startswith('=') and ':' not in line:
                return line.strip()
        return ""

    async def _load_saved(self, widget):
        storage = self._get_storage()
        if not storage or not self.app.client:
            return
        data = storage.load_wallet()
        if data:
            try:
                result = self.app.client.connect_wallet(data['mnemonic'])
                await self.app.main_window.dialog(toga.InfoDialog("Loaded", f"Wallet: {result['address']}"))
                self.app.update_wallet_status()
                self.app._show_wallet()
            except Exception as e:
                await self.app.main_window.dialog(toga.ErrorDialog("Error", f"Failed: {e}"))

    async def _delete_saved(self, widget):
        storage = self._get_storage()
        if not storage:
            return
        if await self.app.main_window.dialog(toga.QuestionDialog(
            "Delete Saved Wallet", "Remove auto-load data? Your actual wallet is NOT deleted."
        )):
            storage.delete_wallet()
            self.app._show_wallet()

    async def _save_wallet(self, widget):
        wallet = self.app.client.get_current_wallet()
        storage = self._get_storage()
        if wallet and storage:
            if await self.app.main_window.dialog(toga.QuestionDialog(
                "Save Wallet", "Save wallet for automatic loading on startup?"
            )):
                if storage.save_wallet(wallet.mnemonic, wallet.address):
                    await self.app.main_window.dialog(toga.InfoDialog("Saved", "Wallet saved for auto-load."))
                    self.app._show_wallet()

    async def _disconnect(self, widget):
        if not self.app.client:
            return
        if await self.app.main_window.dialog(toga.QuestionDialog(
            "Disconnect", "Are you sure you want to disconnect your wallet?"
        )):
            self.app.client.disconnect_wallet()
            self.app.update_wallet_status()
            self.app._show_wallet()

    def _refresh_balance(self, widget):
        asyncio.create_task(self._load_balance())

    async def _load_balance(self):
        if not self.app.client or not self.balance_label:
            return
        self.balance_label.text = "Loading..."
        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(None, self.app.client.get_wallet_balance)
            if status == 200:
                self.balance_label.text = f"{result.get('balance', 0)} BZT"
            else:
                self.balance_label.text = f"Error: {result.get('error', 'unknown')}"
        except Exception as e:
            self.balance_label.text = f"Error: {e}"
