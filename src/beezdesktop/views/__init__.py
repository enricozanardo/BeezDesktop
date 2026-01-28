"""
BeezDesktop Views

Each view provides a specific feature of the application:
- Dashboard: Quick overview and actions
- Wallet: Wallet management
- Files: File upload/download
- Transactions: Transaction history and sending
- Blockchain: Block explorer
- Network: Network status
"""

from beezdesktop.views.dashboard import DashboardView
from beezdesktop.views.wallet import WalletView
from beezdesktop.views.files import FilesView
from beezdesktop.views.transactions import TransactionsView
from beezdesktop.views.blockchain import BlockchainView
from beezdesktop.views.network import NetworkView

__all__ = [
    "DashboardView",
    "WalletView",
    "FilesView",
    "TransactionsView",
    "BlockchainView",
    "NetworkView",
]
