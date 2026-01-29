"""
Wallet View

Wallet management: create, connect, disconnect, view balance.
Features wallet persistence and export functionality.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import asyncio
import os
from pathlib import Path


class WalletView:
    """Wallet management view."""
    
    def __init__(self, app):
        self.app = app
        self.mnemonic_input = None
        self.balance_label = None
        self.address_label = None
        self._wallet_storage = None
    
    def _get_wallet_storage(self):
        """Lazy load wallet storage."""
        if self._wallet_storage is None:
            try:
                from shared.client_core.wallet_storage import get_wallet_storage
                self._wallet_storage = get_wallet_storage()
            except ImportError:
                print("[WALLET] Warning: wallet_storage not available", flush=True)
        return self._wallet_storage
    
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
        
        # Check for saved wallet
        storage = self._get_wallet_storage()
        if storage and storage.has_saved_wallet():
            saved_section = toga.Box(style=Pack(direction=COLUMN, padding=10, background_color="#e8f5e9"))
            saved_section.add(toga.Label(
                "Saved Wallet Found",
                style=Pack(font_size=16, font_weight="bold", padding=(0, 0, 10, 0))
            ))
            saved_section.add(toga.Label(
                "You have a previously saved wallet.",
                style=Pack(padding=(0, 0, 10, 0), color="#2e7d32")
            ))
            
            load_btn = toga.Button(
                "Load Saved Wallet",
                on_press=self._on_load_saved_wallet,
                style=Pack(width=200, padding=(0, 0, 10, 0))
            )
            saved_section.add(load_btn)
            
            delete_btn = toga.Button(
                "Delete Saved Wallet",
                on_press=self._on_delete_saved_wallet,
                style=Pack(width=200)
            )
            saved_section.add(delete_btn)
            
            box.add(saved_section)
            box.add(toga.Box(style=Pack(height=20)))  # Spacer
        
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
        
        # Import wallet section
        import_header = toga.Label(
            "Import Wallet from File",
            style=Pack(font_size=16, font_weight="bold", padding=(20, 0, 10, 0))
        )
        box.add(import_header)
        
        import_btn = toga.Button(
            "Import Wallet File",
            on_press=self._on_import_wallet_file,
            style=Pack(width=200, padding=(0, 0, 20, 0))
        )
        box.add(import_btn)
        
        # Connect existing wallet section
        connect_header = toga.Label(
            "Connect with Mnemonic",
            style=Pack(font_size=16, font_weight="bold", padding=(20, 0, 10, 0))
        )
        box.add(connect_header)
        
        mnemonic_label = toga.Label(
            "Enter your 12-word mnemonic phrase:",
            style=Pack(padding=(0, 0, 5, 0))
        )
        box.add(mnemonic_label)
        
        self.mnemonic_input = toga.MultilineTextInput(
            placeholder="word1 word2 word3 ... (paste with Ctrl+V)",
            style=Pack(width=450, height=80, padding=(0, 0, 10, 0))
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
        
        # Address (in selectable text input for easy copy)
        address_label = toga.Label("Address:", style=Pack(font_weight="bold", padding=(5, 0, 5, 0)))
        box.add(address_label)
        
        address_text = wallet.address if wallet else ""
        self.address_input = toga.TextInput(
            value=address_text,
            readonly=True,
            style=Pack(width=400, padding=(0, 0, 10, 0))
        )
        box.add(self.address_input)
        
        address_note = toga.Label(
            "Select and Ctrl+C to copy",
            style=Pack(font_size=10, color="#888888", padding=(0, 0, 10, 0))
        )
        box.add(address_note)
        
        # Balance
        balance_row = toga.Box(style=Pack(direction=ROW, padding=5))
        balance_label = toga.Label("Balance: ", style=Pack(font_weight="bold"))
        balance_row.add(balance_label)
        self.balance_label = toga.Label("Loading...")
        balance_row.add(self.balance_label)
        box.add(balance_row)
        
        # Action buttons
        actions_row = toga.Box(style=Pack(direction=ROW, padding=(10, 0, 0, 0)))
        
        refresh_btn = toga.Button(
            "Refresh Balance",
            on_press=self._on_refresh_balance,
            style=Pack(width=140, padding=(0, 5, 0, 0))
        )
        actions_row.add(refresh_btn)
        
        export_btn = toga.Button(
            "Export Wallet",
            on_press=self._on_export_wallet,
            style=Pack(width=140, padding=(0, 5, 0, 0))
        )
        actions_row.add(export_btn)
        
        box.add(actions_row)
        
        # Save wallet checkbox
        storage = self._get_wallet_storage()
        if storage:
            save_row = toga.Box(style=Pack(direction=ROW, padding=(15, 0, 0, 0)))
            
            is_saved = storage.has_saved_wallet()
            save_status = "✓ Wallet saved for auto-load" if is_saved else "Wallet not saved"
            save_color = "#2e7d32" if is_saved else "#666666"
            
            save_label = toga.Label(save_status, style=Pack(padding=(5, 10, 5, 0), color=save_color))
            save_row.add(save_label)
            
            if not is_saved:
                save_btn = toga.Button(
                    "Save for Auto-load",
                    on_press=self._on_save_wallet,
                    style=Pack(width=140)
                )
                save_row.add(save_btn)
            
            box.add(save_row)
        
        # Disconnect button
        disconnect_btn = toga.Button(
            "Disconnect Wallet",
            on_press=self._on_disconnect_wallet,
            style=Pack(width=150, padding=(20, 0, 0, 0))
        )
        box.add(disconnect_btn)
        
        # Auto-refresh balance
        asyncio.create_task(self._refresh_balance_async())
        
        return box
    
    async def _on_create_wallet(self, widget):
        """Handle create wallet button."""
        if not self.app.client:
            return
        
        result = self.app.client.create_wallet()
        mnemonic = result['mnemonic']
        address = result['address']
        
        # Ask user to export wallet
        await self._show_wallet_export_dialog(address, mnemonic, is_new=True)
        
        self.app.update_wallet_status()
        self.app._show_wallet()
    
    async def _show_wallet_export_dialog(self, address: str, mnemonic: str, is_new: bool = False):
        """Show dialog to export wallet to file."""
        title = "New Wallet Created!" if is_new else "Export Wallet"
        
        message = (
            f"Address: {address}\n\n"
            f"⚠️ IMPORTANT: Save your wallet backup!\n\n"
            "Would you like to export your wallet to a file?\n"
            "This will create a backup file with your mnemonic phrase."
        )
        
        export = await self.app.main_window.dialog(
            toga.QuestionDialog(title, message)
        )
        
        if export:
            await self._export_wallet_to_file(address, mnemonic)
        else:
            # Show mnemonic in dialog as fallback
            await self.app.main_window.dialog(
                toga.InfoDialog(
                    "Wallet Information",
                    f"Address: {address}\n\n"
                    f"Mnemonic:\n{mnemonic}\n\n"
                    "⚠️ WRITE THIS DOWN! This is the only way to recover your wallet."
                )
            )
    
    async def _export_wallet_to_file(self, address: str, mnemonic: str):
        """Export wallet to file."""
        try:
            # Get save location
            save_path = await self.app.main_window.dialog(
                toga.SaveFileDialog(
                    title="Save Wallet Backup",
                    suggested_filename=f"beez_wallet_{address[:8]}.txt",
                    file_types=["txt"]
                )
            )
            
            if save_path:
                storage = self._get_wallet_storage()
                if storage:
                    success = storage.export_wallet(str(save_path), mnemonic, address)
                else:
                    # Fallback export
                    with open(str(save_path), 'w') as f:
                        f.write(f"=== BEEZ WALLET BACKUP ===\n")
                        f.write(f"Address: {address}\n\n")
                        f.write(f"Mnemonic (12 words):\n{mnemonic}\n\n")
                        f.write(f"=== KEEP THIS FILE SECURE ===\n")
                    success = True
                
                if success:
                    await self.app.main_window.dialog(
                        toga.InfoDialog("Success", f"Wallet exported to:\n{save_path}")
                    )
                else:
                    await self.app.main_window.dialog(
                        toga.ErrorDialog("Error", "Failed to export wallet")
                    )
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Export failed: {e}")
            )
    
    async def _on_export_wallet(self, widget):
        """Handle export wallet button."""
        if not self.app.client:
            return
        
        wallet = self.app.client.get_current_wallet()
        if wallet:
            await self._export_wallet_to_file(wallet.address, wallet.mnemonic)
    
    async def _on_save_wallet(self, widget):
        """Save wallet for auto-load."""
        if not self.app.client:
            return
        
        wallet = self.app.client.get_current_wallet()
        storage = self._get_wallet_storage()
        
        if wallet and storage:
            confirm = await self.app.main_window.dialog(
                toga.QuestionDialog(
                    "Save Wallet",
                    "Save wallet for automatic loading on next startup?\n\n"
                    "The wallet will be stored securely on this device."
                )
            )
            
            if confirm:
                success = storage.save_wallet(wallet.mnemonic, wallet.address)
                if success:
                    await self.app.main_window.dialog(
                        toga.InfoDialog("Success", "Wallet saved for auto-load.")
                    )
                    self.app._show_wallet()  # Refresh view
                else:
                    await self.app.main_window.dialog(
                        toga.ErrorDialog("Error", "Failed to save wallet.")
                    )
    
    async def _on_load_saved_wallet(self, widget):
        """Load saved wallet."""
        storage = self._get_wallet_storage()
        if not storage or not self.app.client:
            return
        
        wallet_data = storage.load_wallet()
        if wallet_data:
            try:
                result = self.app.client.connect_wallet(wallet_data['mnemonic'])
                await self.app.main_window.dialog(
                    toga.InfoDialog("Success", f"Wallet loaded!\nAddress: {result['address']}")
                )
                self.app.update_wallet_status()
                self.app._show_wallet()
            except Exception as e:
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Error", f"Failed to load wallet: {e}")
                )
    
    async def _on_delete_saved_wallet(self, widget):
        """Delete saved wallet."""
        storage = self._get_wallet_storage()
        if not storage:
            return
        
        confirm = await self.app.main_window.dialog(
            toga.QuestionDialog(
                "Delete Saved Wallet",
                "Are you sure you want to delete the saved wallet?\n\n"
                "This will NOT delete your actual wallet, just the auto-load data."
            )
        )
        
        if confirm:
            storage.delete_wallet()
            await self.app.main_window.dialog(
                toga.InfoDialog("Success", "Saved wallet deleted.")
            )
            self.app._show_wallet()  # Refresh view
    
    async def _on_import_wallet_file(self, widget):
        """Import wallet from file."""
        try:
            file_path = await self.app.main_window.dialog(
                toga.OpenFileDialog(
                    title="Import Wallet Backup",
                    file_types=["txt"],
                    multiple_select=False
                )
            )
            
            if file_path:
                with open(str(file_path), 'r') as f:
                    content = f.read()
                
                # Parse mnemonic from file
                mnemonic = self._extract_mnemonic_from_backup(content)
                
                if mnemonic:
                    result = self.app.client.connect_wallet(mnemonic)
                    await self.app.main_window.dialog(
                        toga.InfoDialog("Success", f"Wallet imported!\nAddress: {result['address']}")
                    )
                    self.app.update_wallet_status()
                    self.app._show_wallet()
                else:
                    await self.app.main_window.dialog(
                        toga.ErrorDialog("Error", "Could not find mnemonic in file.")
                    )
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Import failed: {e}")
            )
    
    def _extract_mnemonic_from_backup(self, content: str) -> str:
        """Extract mnemonic from backup file content."""
        lines = content.strip().split('\n')
        
        for i, line in enumerate(lines):
            # Look for mnemonic line
            if 'mnemonic' in line.lower() and i + 1 < len(lines):
                mnemonic_line = lines[i + 1].strip()
                words = mnemonic_line.split()
                if len(words) in [12, 24]:
                    return mnemonic_line
            
            # Check if line itself is a mnemonic
            words = line.strip().split()
            if len(words) in [12, 24] and not line.startswith('=') and ':' not in line:
                return line.strip()
        
        return ""
    
    async def _on_connect_wallet(self, widget):
        """Handle connect wallet button."""
        if not self.app.client or not self.mnemonic_input:
            return
        
        mnemonic = self.mnemonic_input.value.strip()
        
        if not mnemonic:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", "Please enter your mnemonic phrase.")
            )
            return
        
        # Validate mnemonic (basic check)
        words = mnemonic.split()
        if len(words) not in [12, 24]:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Mnemonic must be 12 or 24 words. You entered {len(words)} words.")
            )
            return
        
        try:
            result = self.app.client.connect_wallet(mnemonic)
            await self.app.main_window.dialog(
                toga.InfoDialog("Success", f"Wallet connected!\nAddress: {result['address']}")
            )
            self.app.update_wallet_status()
            self.app._show_wallet()
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed to connect wallet: {e}")
            )
    
    def _on_disconnect_wallet(self, widget):
        """Handle disconnect wallet button."""
        if not self.app.client:
            return
        
        self.app.client.disconnect_wallet()
        self.app.update_wallet_status()
        self.app._show_wallet()
    
    def _on_refresh_balance(self, widget):
        """Handle refresh balance button."""
        asyncio.create_task(self._refresh_balance_async())
    
    async def _refresh_balance_async(self):
        """Refresh the wallet balance asynchronously."""
        if not self.app.client or not self.balance_label:
            return
        
        self.balance_label.text = "Loading..."
        
        loop = asyncio.get_event_loop()
        try:
            result, status = await loop.run_in_executor(
                None, self.app.client.get_wallet_balance
            )
            
            if status == 200:
                balance = result.get('balance', 0)
                self.balance_label.text = f"{balance} BZT"
            else:
                error = result.get('error', 'Unknown error')
                self.balance_label.text = f"Error: {error}"
                print(f"[WALLET] Balance error: {error}", flush=True)
        except Exception as e:
            self.balance_label.text = f"Error: {e}"
            print(f"[WALLET] Balance exception: {e}", flush=True)
