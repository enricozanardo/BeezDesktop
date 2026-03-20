"""
BeezDesktop Main Application

Native desktop client for the Beez Network.
"""

import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from beezdesktop.logging_config import setup_logging, get_log_path

logger = setup_logging()

try:
    from shared.client_core import BeezClientCore, ClientState, Wallet
    from shared.client_core.zmq import start_consensus_listener
except ImportError as e:
    logger.warning("Could not import shared.client_core: %s", e)
    BeezClientCore = None
    ClientState = None

from beezdesktop import __version__
from beezdesktop.theme import Colors, Font, Spacing, NAV_ICONS, SIDEBAR_WIDTH


class BeezDesktopApp(toga.App):
    """Main Beez Desktop Application."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.state = ClientState() if ClientState else None
        self.client = BeezClientCore(state=self.state) if BeezClientCore else None
        self.current_view = "dashboard"
        self._nav_buttons = {}

    def startup(self):
        """Initialize the application UI."""
        logger.info("BeezDesktop v%s starting up", __version__)
        logger.info("Log file: %s", get_log_path())
        self.main_window = toga.MainWindow(
            title=f"{self.formal_name} v{__version__}",
            size=(1200, 780),
        )

        root = toga.Box(style=Pack(direction=ROW, flex=1))

        sidebar = self._build_sidebar()
        root.add(sidebar)

        # Content area wrapped in a ScrollContainer so views can scroll
        self._scroll = toga.ScrollContainer(
            horizontal=False,
            style=Pack(flex=1),
        )
        self.content_area = toga.Box(
            style=Pack(
                direction=COLUMN,
                padding=Spacing.PAGE_PADDING,
                background_color=Colors.BG_PAGE,
            )
        )
        self._scroll.content = self.content_area
        root.add(self._scroll)

        self._show_dashboard()

        self.main_window.content = root
        self.main_window.show()

        self._init_config()
        self._start_background_services()
        self._auto_load_wallet()

    # ------------------------------------------------------------------ #
    # SIDEBAR
    # ------------------------------------------------------------------ #

    def _build_sidebar(self) -> toga.Box:
        sidebar = toga.Box(
            style=Pack(
                direction=COLUMN,
                width=SIDEBAR_WIDTH,
                padding=0,
                background_color=Colors.SIDEBAR_BG,
            )
        )

        # Brand header
        brand = toga.Box(style=Pack(direction=COLUMN, padding=(Spacing.LG, Spacing.MD, Spacing.XS, Spacing.MD)))
        brand_title = toga.Label(
            "BEEZ",
            style=Pack(font_size=24, font_weight="bold", color=Colors.ACCENT),
        )
        brand.add(brand_title)

        brand_sub = toga.Label(
            "Desktop",
            style=Pack(font_size=Font.SIZE_BODY, color=Colors.TEXT_ON_DARK),
        )
        brand.add(brand_sub)
        sidebar.add(brand)

        version_label = toga.Label(
            f"v{__version__}",
            style=Pack(padding=(0, Spacing.MD, Spacing.MD, Spacing.MD), font_size=Font.SIZE_CAPTION, color=Colors.TEXT_MUTED),
        )
        sidebar.add(version_label)

        # Divider
        sidebar.add(toga.Box(style=Pack(height=1, background_color="#1e2d50")))

        # Navigation items
        nav_items = [
            ("Dashboard",    "dashboard",    self._show_dashboard),
            ("Wallet",       "wallet",       self._show_wallet),
            ("Files",        "files",        self._show_files),
            ("Smart",        "smart",        self._show_smart),
            ("Knowledge",    "knowledge",    self._show_knowledge),
            ("Transactions", "transactions", self._show_transactions),
            ("Blockchain",   "blockchain",   self._show_blockchain),
            ("Network",      "network",      self._show_network),
            ("Settings",     "settings",     self._show_settings),
        ]

        nav_box = toga.Box(style=Pack(direction=COLUMN, padding=(Spacing.XS, 0)))
        for label, view_id, handler in nav_items:
            btn = self._nav_button(label, view_id, handler)
            nav_box.add(btn)
        sidebar.add(nav_box)

        # Flexible spacer pushes status to bottom
        sidebar.add(toga.Box(style=Pack(flex=1)))

        # Wallet status at bottom
        self.wallet_status_label = toga.Label(
            "No wallet connected",
            style=Pack(
                padding=(Spacing.SM, Spacing.MD, Spacing.MD, Spacing.MD),
                font_size=Font.SIZE_CAPTION,
                color=Colors.TEXT_MUTED,
            ),
        )
        sidebar.add(self.wallet_status_label)

        return sidebar

    def _nav_button(self, label: str, view_id: str, handler) -> toga.Button:
        icon = NAV_ICONS.get(view_id, "")
        text = f" {icon}  {label}"

        is_active = self.current_view == view_id
        bg = Colors.SIDEBAR_BTN_ACTIVE if is_active else Colors.SIDEBAR_BTN
        fg = Colors.SIDEBAR_TEXT_ACTIVE if is_active else Colors.SIDEBAR_TEXT

        btn = toga.Button(
            text,
            on_press=handler,
            style=Pack(
                padding=(Spacing.SM, Spacing.MD),
                color=fg,
                background_color=bg,
                font_size=Font.SIZE_BODY,
            ),
        )
        self._nav_buttons[view_id] = btn
        return btn

    def _set_active_nav(self, view_id: str):
        """Highlight the active navigation button."""
        for vid, btn in self._nav_buttons.items():
            if vid == view_id:
                btn.style.background_color = Colors.SIDEBAR_BTN_ACTIVE
                btn.style.color = Colors.SIDEBAR_TEXT_ACTIVE
            else:
                btn.style.background_color = Colors.SIDEBAR_BTN
                btn.style.color = Colors.SIDEBAR_TEXT

    # ------------------------------------------------------------------ #
    # VIEW SWITCHING
    # ------------------------------------------------------------------ #

    def _clear_content(self):
        """Clear the content area and cancel any active view refresh tasks."""
        if hasattr(self, '_active_view') and self._active_view is not None:
            view = self._active_view
            if hasattr(view, '_auto_refresh_enabled'):
                view._auto_refresh_enabled = False
            if hasattr(view, '_refresh_task') and view._refresh_task is not None:
                view._refresh_task.cancel()
                view._refresh_task = None
        self._active_view = None

        for child in list(self.content_area.children):
            self.content_area.remove(child)

    def _switch_view(self, view_id: str, view_class_path: str, view_class_name: str, widget=None):
        """Generic view switcher to reduce boilerplate."""
        self._clear_content()
        self.current_view = view_id
        self._set_active_nav(view_id)

        import importlib
        mod = importlib.import_module(view_class_path)
        cls = getattr(mod, view_class_name)
        view = cls(app=self)
        self._active_view = view
        self.content_area.add(view.build())

        # Reset scroll position to top
        if hasattr(self, '_scroll'):
            self._scroll.position = (0, 0)

    def _show_dashboard(self, widget=None):
        self._switch_view("dashboard", "beezdesktop.views.dashboard", "DashboardView", widget)

    def _show_wallet(self, widget=None):
        self._switch_view("wallet", "beezdesktop.views.wallet", "WalletView", widget)

    def _show_files(self, widget=None):
        self._switch_view("files", "beezdesktop.views.files", "FilesView", widget)

    def _show_smart(self, widget=None):
        self._switch_view("smart", "beezdesktop.views.smart", "SmartView", widget)

    def _show_knowledge(self, widget=None):
        self._switch_view("knowledge", "beezdesktop.views.knowledge", "KnowledgeView", widget)

    def _show_transactions(self, widget=None):
        self._switch_view("transactions", "beezdesktop.views.transactions", "TransactionsView", widget)

    def _show_blockchain(self, widget=None):
        self._switch_view("blockchain", "beezdesktop.views.blockchain", "BlockchainView", widget)

    def _show_network(self, widget=None):
        self._switch_view("network", "beezdesktop.views.network", "NetworkView", widget)

    def _show_settings(self, widget=None):
        self._switch_view("settings", "beezdesktop.views.settings", "SettingsView", widget)

    # ------------------------------------------------------------------ #
    # CONFIG / SERVICES / WALLET
    # ------------------------------------------------------------------ #

    def _init_config(self):
        """Load .beez config, creating from bundled defaults on first launch."""
        try:
            from shared.beez_config import get_config
            config = get_config()
            nodes = config.network.directory_nodes
            logger.info("Config loaded: %d directory nodes", len(nodes))
        except Exception as e:
            logger.error("Config init error: %s", e)

    def _start_background_services(self):
        """Start background services like consensus listener."""
        if self.state:
            try:
                def on_consensus(data):
                    storage = len(self.state.active_nodes)
                    chain = len(self.state.chain_nodes)
                    logger.debug("Consensus update: %d storage, %d chain nodes", storage, chain)

                start_consensus_listener(state=self.state, callback=on_consensus)
                logger.info("Consensus listener started")
            except Exception as e:
                logger.error("Could not start consensus: %s", e)

    def update_wallet_status(self):
        """Update the wallet status display in sidebar."""
        if self.client and self.client.is_wallet_connected():
            wallet = self.client.get_current_wallet()
            addr = wallet.address[:12] + "..." if wallet else ""
            self.wallet_status_label.text = f"\u25C8 {addr}"
            self.wallet_status_label.style.color = Colors.STATUS_ONLINE
        else:
            self.wallet_status_label.text = "No wallet connected"
            self.wallet_status_label.style.color = Colors.TEXT_MUTED

    def _auto_load_wallet(self):
        """Auto-load saved wallet on startup."""
        try:
            from shared.client_core.wallet_storage import get_wallet_storage
            storage = get_wallet_storage()

            if storage.has_saved_wallet() and self.client:
                wallet_data = storage.load_wallet()
                if wallet_data:
                    self.client.connect_wallet(wallet_data['mnemonic'])
                    self.update_wallet_status()
                    logger.info("Auto-loaded wallet: %s...", wallet_data.get('address', '')[:16])
        except Exception as e:
            logger.error("Could not auto-load wallet: %s", e)


def main():
    """Application entry point."""
    return BeezDesktopApp(
        formal_name="Beez Desktop",
        app_id="io.beez.beezdesktop",
        app_name="beezdesktop",
        icon="resources/beezdesktop",
    )


if __name__ == "__main__":
    main().main_loop()
