"""
Network View

Network status: node counts, connectivity, health.
Uses SearchableTable for browsing node lists with search and pagination.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from beezdesktop.theme import (
    Colors, Font, Spacing,
    page_header, card, stat_card, status_badge, spacer,
    secondary_button, SearchableTable,
)


class NetworkView:
    """Network status view."""

    def __init__(self, app):
        self.app = app

    def build(self) -> toga.Box:
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        header_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, Spacing.SECTION_GAP, 0), alignment="center"))
        header_row.add(toga.Label(
            "Network Status",
            style=Pack(font_size=Font.SIZE_H1, font_weight="bold", color=Colors.TEXT_PRIMARY, flex=1),
        ))
        header_row.add(secondary_button("Refresh", self._on_refresh, width=100))
        container.add(header_row)

        container.add(self._connection_card())
        container.add(spacer(Spacing.SM))
        container.add(self._stat_row())
        container.add(spacer(Spacing.SECTION_GAP))
        container.add(self._node_lists())

        return container

    def _connection_card(self) -> toga.Box:
        total = self._total_nodes()
        if total > 0:
            return card(
                bg=Colors.SURFACE_SUCCESS,
                children=[status_badge(f"Connected to network ({total} nodes)", online=True)],
            )
        return card(
            bg=Colors.SURFACE_WARNING,
            children=[
                status_badge("Waiting for consensus...", online=False),
                toga.Label(
                    "Consensus updates every ~30 s. Make sure the network is running.",
                    style=Pack(font_size=Font.SIZE_SMALL, color=Colors.TEXT_MUTED, padding=(Spacing.XS, 0, 0, 0)),
                ),
            ],
        )

    def _stat_row(self) -> toga.Box:
        storage = len(self.app.state.active_nodes) if self.app.state else 0
        chain = len(self.app.state.chain_nodes) if self.app.state else 0
        dam = len(self.app.state.manager_nodes) if self.app.state else 0
        smart = len(self.app.state.smart_nodes) if self.app.state else 0

        row = toga.Box(style=Pack(direction=ROW))
        cards = [
            ("Storage", str(storage), "#2e7d32", Colors.SURFACE_SUCCESS),
            ("Chain", str(chain), "#1565c0", "#e8eaf6"),
            ("DAM", str(dam), "#e65100", Colors.SURFACE_WARNING),
            ("Smart", str(smart), "#6a1b9a", "#f3e5f5"),
        ]
        for i, (label, val, color, bg) in enumerate(cards):
            if i > 0:
                row.add(toga.Box(style=Pack(width=Spacing.SM)))
            row.add(stat_card(label, val, color=color, bg=bg))
        return row

    def _node_lists(self) -> toga.Box:
        section = toga.Box(style=Pack(direction=COLUMN))

        node_groups = [
            ("Storage Nodes", self.app.state.active_nodes if self.app.state else []),
            ("Chain Nodes", self.app.state.chain_nodes if self.app.state else []),
            ("DAM Nodes", self.app.state.manager_nodes if self.app.state else []),
            ("Smart Nodes", self.app.state.smart_nodes if self.app.state else []),
        ]

        for group_name, nodes in node_groups:
            if not nodes:
                continue

            group_card = card(title=f"{group_name} ({len(nodes)})", bg=Colors.BG_CARD)

            data = []
            for n in nodes:
                if isinstance(n, dict):
                    node_id = n.get("node_id", "unknown")
                    ip = n.get("ip", "unknown")
                    rep = n.get("reputation", 100.0)
                    wallet = n.get("wallet_address", "")
                    data.append((
                        node_id[:20] + ("..." if len(node_id) > 20 else ""),
                        ip,
                        f"{rep:.0f}",
                        (wallet[:14] + "...") if wallet else "--",
                    ))

            if data:
                st = SearchableTable(
                    headings=["Node ID", "IP", "Reputation", "Wallet"],
                    page_size=10,
                    search_placeholder=f"Search {group_name.lower()}...",
                    table_height=180,
                )
                st.set_data(data)
                group_card.add(st.box)
            else:
                group_card.add(toga.Label(
                    "No detailed node data available",
                    style=Pack(font_size=Font.SIZE_SMALL, color=Colors.TEXT_MUTED),
                ))

            section.add(group_card)
            section.add(spacer(Spacing.SM))

        if not any(nodes for _, nodes in node_groups):
            section.add(toga.Label(
                "No nodes discovered yet. The consensus listener refreshes every ~30 s.",
                style=Pack(font_size=Font.SIZE_BODY, color=Colors.TEXT_MUTED, padding=Spacing.MD),
            ))

        return section

    def _total_nodes(self) -> int:
        if not self.app.state:
            return 0
        return (
            len(self.app.state.active_nodes)
            + len(self.app.state.chain_nodes)
            + len(self.app.state.manager_nodes)
            + len(self.app.state.smart_nodes)
        )

    def _on_refresh(self, widget):
        self.app._show_network()
