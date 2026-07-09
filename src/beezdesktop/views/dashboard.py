"""
Dashboard View

Landing page with wallet summary, network stats, and quick actions.
"""

import asyncio

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from beezdesktop.theme import (
    Colors, Font, Spacing,
    page_header, card, stat_card, status_badge,
    action_card, info_row, spacer,
)
from beezdesktop.views.lifecycle import ViewLifecycle


class DashboardView(ViewLifecycle):
    """Dashboard view with quick actions and overview."""

    def __init__(self, app):
        ViewLifecycle.__init__(self, app)

    def build(self) -> toga.Box:
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        container.add(page_header("Dashboard", "Welcome to the Beez Network"))

        # Cards are attached incrementally so the view switch stays
        # inside the 250ms UI-thread budget (audit D-04/D-05).
        self._body_box = toga.Box(style=Pack(direction=COLUMN))
        container.add(self._body_box)
        self.spawn_task(self._populate_sections(), name="dashboard-sections")

        return container

    async def _populate_sections(self) -> None:
        """Attach the dashboard body with a single repaint.

        One ``await`` lets the event loop paint the skeleton (header)
        first; the body is then built fully detached and attached with
        a single ``add`` so the content appears in one repaint instead
        of card-by-card (review feedback: incremental attach reads as
        flickering).
        """
        await asyncio.sleep(0)
        if self._destroyed:
            return

        sections = []
        if self.app.client and self.app.client.is_wallet_connected():
            sections.append(self._wallet_summary)
        sections.extend([
            self._stat_cards_row,
            self._quick_actions_section,
            self._network_health_section,
        ])

        body = toga.Box(style=Pack(direction=COLUMN))
        first = True
        for build_section in sections:
            if not first:
                body.add(spacer(Spacing.SECTION_GAP))
            first = False
            body.add(build_section())

        if self._destroyed:
            return
        self._body_box.add(body)

    def _wallet_summary(self) -> toga.Box:
        wallet = self.app.client.get_current_wallet()
        addr = wallet.address if wallet else "Unknown"
        box = card(title="Connected Wallet", bg=Colors.SURFACE_INFO)
        box.add(info_row("Address", addr, label_width=80))
        return box

    def _stat_cards_row(self) -> toga.Box:
        storage = len(self.app.state.active_nodes) if self.app.state else 0
        chain = len(self.app.state.chain_nodes) if self.app.state else 0
        dam = len(self.app.state.manager_nodes) if self.app.state else 0
        smart = len(self.app.state.smart_nodes) if self.app.state else 0
        total = storage + chain + dam + smart

        row = toga.Box(style=Pack(direction=ROW))
        cards = [
            ("Total Nodes", str(total), Colors.PRIMARY, Colors.SURFACE_INFO),
            ("Chain", str(chain), "#1565c0", "#e8eaf6"),
            ("Storage", str(storage), "#2e7d32", Colors.SURFACE_SUCCESS),
            ("DAM", str(dam), "#e65100", Colors.SURFACE_WARNING),
            ("Smart", str(smart), "#6a1b9a", "#f3e5f5"),
        ]
        for i, (label, value, color, bg) in enumerate(cards):
            if i > 0:
                row.add(toga.Box(style=Pack(width=Spacing.SM)))
            row.add(stat_card(label, value, color=color, bg=bg))
        return row

    def _quick_actions_section(self) -> toga.Box:
        section = toga.Box(style=Pack(direction=COLUMN))
        section.add(toga.Label(
            "Quick Actions",
            style=Pack(font_size=Font.SIZE_H2, font_weight="bold", color=Colors.TEXT_PRIMARY, padding=(0, 0, Spacing.MD, 0)),
        ))

        row = toga.Box(style=Pack(direction=ROW))
        actions = [
            ("Wallet", "Create or connect a wallet", "Open Wallet", self._on_wallet, "\u25C8"),
            ("Upload File", "Encrypt and upload files", "Upload", self._on_upload, "\u25B2"),
            ("Send BZT", "Transfer tokens", "Send", self._on_send, "\u21C4"),
            ("Explorer", "Browse blocks & TXs", "Explore", self._on_explorer, "\u26D3"),
        ]
        for i, (title, desc, btn_text, handler, icon) in enumerate(actions):
            if i > 0:
                row.add(toga.Box(style=Pack(width=Spacing.SM)))
            row.add(action_card(title=title, description=desc, button_text=btn_text, handler=handler, icon=icon))

        section.add(row)
        return section

    def _network_health_section(self) -> toga.Box:
        total = 0
        if self.app.state:
            total = (
                len(self.app.state.active_nodes)
                + len(self.app.state.chain_nodes)
                + len(self.app.state.manager_nodes)
                + len(self.app.state.smart_nodes)
            )

        health_card = card(title="Network Health", bg=Colors.BG_CARD)
        if total > 0:
            health_card.add(status_badge(f"Connected to {total} nodes", online=True))
        else:
            health_card.add(status_badge("Waiting for consensus...", online=False))
            health_card.add(toga.Label(
                "The consensus listener refreshes every ~30 s. Make sure the network is running.",
                style=Pack(font_size=Font.SIZE_SMALL, color=Colors.TEXT_MUTED, padding=(Spacing.XS, 0, 0, 0)),
            ))

        btn_row = toga.Box(style=Pack(direction=ROW, padding=(Spacing.MD, 0, 0, 0)))
        btn_row.add(toga.Button(
            "Refresh",
            on_press=lambda w: self.app._show_dashboard(),
            style=Pack(width=100, padding=Spacing.XS, background_color=Colors.BG_HEADER),
        ))
        health_card.add(btn_row)
        return health_card

    def _on_wallet(self, widget):
        self.app._show_wallet()

    def _on_upload(self, widget):
        self.app._show_files()

    def _on_send(self, widget):
        self.app._show_transactions()

    def _on_explorer(self, widget):
        self.app._show_blockchain()