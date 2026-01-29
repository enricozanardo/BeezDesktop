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
        self.nodes_table = None
        self.stat_labels = {}
    
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
        
        # Connection status
        status_section = self._build_connection_status()
        container.add(status_section)
        
        # Node stats
        stats_section = self._build_stats_section()
        container.add(stats_section)
        
        # Node lists
        nodes_section = self._build_nodes_section()
        container.add(nodes_section)
        
        return container
    
    def _build_connection_status(self) -> toga.Box:
        """Build the connection status indicator."""
        section = toga.Box(
            style=Pack(direction=ROW, padding=10, background_color="#e8f5e9")
        )
        
        total_nodes = 0
        if self.app.state:
            total_nodes = (
                len(self.app.state.active_nodes) +
                len(self.app.state.chain_nodes) +
                len(self.app.state.manager_nodes)
            )
        
        if total_nodes > 0:
            status_icon = toga.Label("●", style=Pack(color="#4caf50", font_size=16, padding=(0, 5, 0, 0)))
            status_text = toga.Label(
                f"Connected to network ({total_nodes} nodes)",
                style=Pack(color="#2e7d32", font_weight="bold")
            )
        else:
            section.style.background_color = "#fff3e0"
            status_icon = toga.Label("●", style=Pack(color="#ff9800", font_size=16, padding=(0, 5, 0, 0)))
            status_text = toga.Label(
                "Waiting for network consensus...",
                style=Pack(color="#e65100", font_weight="bold")
            )
        
        section.add(status_icon)
        section.add(status_text)
        
        return section
    
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
            ("Storage Nodes", storage_count, "#2196f3"),
            ("Chain Nodes", chain_count, "#4caf50"),
            ("DAM Nodes", dam_count, "#ff9800"),
        ]
        
        for label, count, color in stats:
            card = self._create_stat_card(label, str(count), color)
            section.add(card)
        
        return section
    
    def _create_stat_card(self, label: str, value: str, color: str) -> toga.Box:
        """Create a stat card widget."""
        card = toga.Box(
            style=Pack(
                direction=COLUMN,
                padding=15,
                width=150,
                background_color="#f5f5f5"
            )
        )
        
        value_label = toga.Label(
            value,
            style=Pack(font_size=32, font_weight="bold", color=color)
        )
        card.add(value_label)
        
        name_label = toga.Label(
            label,
            style=Pack(font_size=12, color="#666666")
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
        
        self.tab_buttons = {}
        for node_type, label in [("storage", "Storage"), ("chain", "Chain"), ("dam", "DAM")]:
            btn = toga.Button(
                label,
                on_press=lambda w, t=node_type: self._show_nodes(t),
                style=Pack(width=100)
            )
            self.tab_buttons[node_type] = btn
            tab_row.add(btn)
        
        section.add(tab_row)
        
        # Node table
        self.nodes_table = toga.Table(
            headings=["Node ID", "IP", "Type", "Score", "Status"],
            data=[],
            style=Pack(flex=1)
        )
        section.add(self.nodes_table)
        
        # Load storage nodes by default
        self._show_nodes("storage")
        
        return section
    
    def _show_nodes(self, node_type: str):
        """Show nodes of a specific type."""
        if not self.app.state or not self.nodes_table:
            return
        
        self.nodes_table.data.clear()
        
        if node_type == "storage":
            nodes = self.app.state.active_nodes
        elif node_type == "chain":
            nodes = self.app.state.chain_nodes
        else:  # dam
            nodes = self.app.state.manager_nodes
        
        for node in nodes:
            node_id = node.get("node_id", "Unknown")
            # Truncate node_id if too long
            display_id = node_id[:20] + "..." if len(node_id) > 20 else node_id
            
            score = node.get("score", 1.0)
            score_str = f"{score:.3f}" if isinstance(score, float) else str(score)
            
            self.nodes_table.data.append([
                display_id,
                node.get("ip", "Unknown"),
                node.get("node_type", node_type),
                score_str,
                "Active" if not node.get("banned", False) else "Banned"
            ])
    
    def _on_refresh(self, widget):
        """Refresh network status."""
        self.app._show_network()  # Rebuild the view
