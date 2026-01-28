"""
Network View

Network status: node counts, connectivity, health.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class NetworkView:
    """Network status view."""
    
    def __init__(self, app):
        self.app = app
    
    def build(self) -> toga.Box:
        """Build the network view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Header
        header_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 20, 0)))
        
        header = toga.Label(
            "Network Status",
            style=Pack(font_size=24, font_weight="bold", flex=1)
        )
        header_row.add(header)
        
        refresh_btn = toga.Button(
            "Refresh",
            on_press=self._on_refresh,
            style=Pack(width=80)
        )
        header_row.add(refresh_btn)
        
        container.add(header_row)
        
        # Node stats
        stats_section = self._build_stats_section()
        container.add(stats_section)
        
        # Node lists
        nodes_section = self._build_nodes_section()
        container.add(nodes_section)
        
        return container
    
    def _build_stats_section(self) -> toga.Box:
        """Build the stats section."""
        section = toga.Box(
            style=Pack(direction=ROW, padding=10)
        )
        
        # Get counts from state
        storage_count = len(self.app.state.active_nodes) if self.app.state else 0
        chain_count = len(self.app.state.chain_nodes) if self.app.state else 0
        dam_count = len(self.app.state.manager_nodes) if self.app.state else 0
        
        stats = [
            ("Storage Nodes", storage_count),
            ("Chain Nodes", chain_count),
            ("DAM Nodes", dam_count),
        ]
        
        for label, count in stats:
            card = self._create_stat_card(label, str(count))
            section.add(card)
        
        return section
    
    def _create_stat_card(self, label: str, value: str) -> toga.Box:
        """Create a stat card widget."""
        card = toga.Box(
            style=Pack(
                direction=COLUMN,
                padding=15,
                width=150,
                background_color="#f5f5f5",
                alignment="center"
            )
        )
        
        value_label = toga.Label(
            value,
            style=Pack(font_size=32, font_weight="bold", text_align="center")
        )
        card.add(value_label)
        
        name_label = toga.Label(
            label,
            style=Pack(font_size=12, color="#666666", text_align="center")
        )
        card.add(name_label)
        
        return card
    
    def _build_nodes_section(self) -> toga.Box:
        """Build the nodes list section."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        
        header = toga.Label(
            "Active Nodes",
            style=Pack(font_size=16, font_weight="bold", padding=(20, 0, 10, 0))
        )
        section.add(header)
        
        # Tabs for different node types
        tab_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        
        storage_btn = toga.Button(
            "Storage",
            on_press=lambda w: self._show_nodes("storage"),
            style=Pack(width=100)
        )
        tab_row.add(storage_btn)
        
        chain_btn = toga.Button(
            "Chain",
            on_press=lambda w: self._show_nodes("chain"),
            style=Pack(width=100)
        )
        tab_row.add(chain_btn)
        
        dam_btn = toga.Button(
            "DAM",
            on_press=lambda w: self._show_nodes("dam"),
            style=Pack(width=100)
        )
        tab_row.add(dam_btn)
        
        section.add(tab_row)
        
        # Node table
        self.nodes_table = toga.Table(
            headings=["Node ID", "IP", "Type", "Status"],
            data=[],
            style=Pack(flex=1)
        )
        section.add(self.nodes_table)
        
        # Load storage nodes by default
        self._show_nodes("storage")
        
        return section
    
    def _show_nodes(self, node_type: str):
        """Show nodes of a specific type."""
        if not self.app.state:
            return
        
        self.nodes_table.data.clear()
        
        if node_type == "storage":
            nodes = self.app.state.active_nodes
        elif node_type == "chain":
            nodes = self.app.state.chain_nodes
        else:  # dam
            nodes = self.app.state.manager_nodes
        
        for node in nodes:
            self.nodes_table.data.append([
                node.get("node_id", "Unknown")[:16] + "...",
                node.get("ip", "Unknown"),
                node.get("node_type", node_type),
                "Active"
            ])
    
    def _on_refresh(self, widget):
        """Refresh network status."""
        self.app._show_network()  # Rebuild the view
