"""
BeezDesktop Components

Reusable UI components:
- dialogs: Custom dialogs (mnemonic display, confirmations)
- widgets: Custom widgets (SelectableLabel, CopyableLabel, InfoRow)
- sidebar: Navigation sidebar (included in app.py)
"""

from beezdesktop.components.dialogs import (
    show_mnemonic_dialog,
    show_confirm_dialog,
    show_error_dialog,
    show_info_dialog,
)

from beezdesktop.components.widgets import (
    SelectableLabel,
    SelectableText,
    CopyableLabel,
    InfoRow,
)

__all__ = [
    # Dialogs
    "show_mnemonic_dialog",
    "show_confirm_dialog",
    "show_error_dialog",
    "show_info_dialog",
    # Widgets (selectable text)
    "SelectableLabel",
    "SelectableText",
    "CopyableLabel",
    "InfoRow",
]
