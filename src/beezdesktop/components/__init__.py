"""
BeezDesktop Components

Reusable UI components:
- dialogs: Custom dialogs (mnemonic display, confirmations)
- sidebar: Navigation sidebar (included in app.py)
"""

from beezdesktop.components.dialogs import (
    show_mnemonic_dialog,
    show_confirm_dialog,
)

__all__ = [
    "show_mnemonic_dialog",
    "show_confirm_dialog",
]
