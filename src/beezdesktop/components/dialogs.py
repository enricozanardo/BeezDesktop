"""
Custom Dialog Components

Provides custom dialogs for the application:
- Mnemonic display dialog
- Confirmation dialogs
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN


def show_mnemonic_dialog(window: toga.Window, mnemonic: str, address: str):
    """
    Show a dialog displaying the mnemonic phrase.
    
    Args:
        window: Parent window
        mnemonic: 12/24 word mnemonic phrase
        address: Wallet address
    """
    message = (
        f"Your new wallet address:\n{address}\n\n"
        f"IMPORTANT: Write down your mnemonic phrase:\n\n"
        f"{mnemonic}\n\n"
        "This is the ONLY way to recover your wallet.\n"
        "Never share it with anyone!"
    )
    
    window.info_dialog(
        "Wallet Created - SAVE YOUR MNEMONIC",
        message
    )


def show_confirm_dialog(window: toga.Window, title: str, message: str) -> bool:
    """
    Show a confirmation dialog.
    
    Args:
        window: Parent window
        title: Dialog title
        message: Dialog message
        
    Returns:
        True if user confirmed, False otherwise
    """
    return window.confirm_dialog(title, message)


def show_error_dialog(window: toga.Window, title: str, message: str):
    """
    Show an error dialog.
    
    Args:
        window: Parent window
        title: Dialog title
        message: Error message
    """
    window.error_dialog(title, message)


def show_info_dialog(window: toga.Window, title: str, message: str):
    """
    Show an info dialog.
    
    Args:
        window: Parent window
        title: Dialog title
        message: Info message
    """
    window.info_dialog(title, message)
