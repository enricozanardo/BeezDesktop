"""
Files View

File management: upload, download, list files with full options.
Includes storage cost calculation with chunk-based pricing and live geolocation.
Split into four tabs: Upload, My Files, Public Files, and Notifications.

Text selection is enabled in detail panels using SelectableLabel/SelectableText components.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import asyncio
import os
import uuid
from datetime import datetime, timedelta

# Import selectable components for text selection support
# Disabled temporarily to debug button issues
SelectableLabel = None
SelectableText = None
InfoRow = None


def safe_create_task(coro, name="unnamed"):
    """Create an async task with error handling."""
    async def wrapper():
        try:
            await coro
        except Exception as e:
            print(f"[FILES] Task '{name}' error: {e}", flush=True)
            import traceback
            traceback.print_exc()
    return asyncio.create_task(wrapper())


def safe_async_handler(handler_func, name="unnamed"):
    """Create a safe button handler that wraps an async function."""
    def wrapper(widget):
        async def inner():
            try:
                await handler_func(widget)
            except Exception as e:
                print(f"[FILES] Handler '{name}' error: {e}", flush=True)
                import traceback
                traceback.print_exc()
        asyncio.create_task(inner())
    return wrapper

# Chunk size in bytes (100KB as per initial_doc.txt)
CHUNK_SIZE = 100 * 1024  # 100KB


class FilesView:
    """File management view with Upload, My Files, Public Files, and Notifications tabs."""
    
    def __init__(self, app):
        self.app = app
        self.files_table = None
        self.public_files_table = None
        self.notifications_table = None
        self.selected_file_path = None
        self.selected_file_size = 0
        
        # Store file data for actions
        self._my_files_data = []
        self._public_files_data = []
        self._notifications_data = []
        
        # Details panels (may use SelectableText or Label)
        self._file_details_text = None
        self._file_details_label = None
        self._public_details_text = None
        self._public_details_label = None
        
        # Upload options
        self.visibility_select = None
        self.price_input = None
        self.duration_input = None
        self.node_select = None
        self.blur_switch = None
        
        # Cost display
        self.cost_label = None
        
        # Selected storage nodes display
        self._selected_nodes_label = None
        
        # Geolocation
        self._user_location = None
        self._location_label = None
        
        # Tab container
        self._tab_container = None
        self._current_tab = "upload"
    
    def build(self) -> toga.Box:
        """Build the files view with tabs."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Header
        header = toga.Label(
            "Files",
            style=Pack(padding=(0, 0, 10, 0), font_size=24, font_weight="bold")
        )
        container.add(header)
        
        # Check if wallet is connected
        if not self.app.client or not self.app.client.is_wallet_connected():
            no_wallet = toga.Label(
                "Please connect a wallet to manage files.",
                style=Pack(padding=20, color="#888888")
            )
            container.add(no_wallet)
            return container
        
        # Create tab buttons
        tab_buttons = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        
        self._upload_tab_btn = toga.Button(
            "Upload",
            on_press=self._show_upload_tab,
            style=Pack(width=100, padding=(0, 5, 0, 0), background_color="#4CAF50")
        )
        tab_buttons.add(self._upload_tab_btn)
        
        self._files_tab_btn = toga.Button(
            "My Files",
            on_press=self._show_files_tab,
            style=Pack(width=100, padding=(0, 5, 0, 0), background_color="#dddddd")
        )
        tab_buttons.add(self._files_tab_btn)
        
        self._public_tab_btn = toga.Button(
            "Public Files",
            on_press=self._show_public_tab,
            style=Pack(width=100, padding=(0, 5, 0, 0), background_color="#dddddd")
        )
        tab_buttons.add(self._public_tab_btn)
        
        self._notifications_tab_btn = toga.Button(
            "Notifications",
            on_press=self._show_notifications_tab,
            style=Pack(width=100, padding=(0, 5, 0, 0), background_color="#dddddd")
        )
        tab_buttons.add(self._notifications_tab_btn)
        
        container.add(tab_buttons)
        
        # Tab content container
        self._tab_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        container.add(self._tab_container)
        
        # Build all sections
        print("[FILES] Building sections...", flush=True)
        try:
            self._upload_section = self._build_upload_section()
            print("[FILES] Upload section built", flush=True)
            self._files_section = self._build_files_section()
            print("[FILES] Files section built", flush=True)
            self._public_section = self._build_public_section()
            print("[FILES] Public section built", flush=True)
            self._notifications_section = self._build_notifications_section()
            print("[FILES] Notifications section built", flush=True)
        except Exception as e:
            print(f"[FILES] ERROR building sections: {e}", flush=True)
            import traceback
            traceback.print_exc()
        
        # Show upload tab by default
        self._tab_container.add(self._upload_section)
        
        # Fetch location in background (with error handling)
        safe_create_task(self._fetch_location(), "fetch_location")
        
        print("[FILES] View built successfully", flush=True)
        return container
    
    def _update_tab_buttons(self, active_tab: str):
        """Update tab button styles based on active tab."""
        tabs = {
            "upload": self._upload_tab_btn,
            "files": self._files_tab_btn,
            "public": self._public_tab_btn,
            "notifications": self._notifications_tab_btn,
        }
        for tab_id, btn in tabs.items():
            if tab_id == active_tab:
                btn.style.background_color = "#4CAF50"
            else:
                btn.style.background_color = "#dddddd"
    
    def _show_upload_tab(self, widget):
        """Switch to upload tab."""
        self._tab_container.clear()
        self._tab_container.add(self._upload_section)
        self._current_tab = "upload"
        self._update_tab_buttons("upload")
    
    def _show_files_tab(self, widget):
        """Switch to files tab."""
        print("[FILES] Switching to My Files tab", flush=True)
        self._tab_container.clear()
        self._tab_container.add(self._files_section)
        self._current_tab = "files"
        self._update_tab_buttons("files")
        safe_create_task(self._load_files_async(), "load_files")
    
    def _show_public_tab(self, widget):
        """Switch to public files tab."""
        print("[FILES] Switching to Public Files tab", flush=True)
        self._tab_container.clear()
        self._tab_container.add(self._public_section)
        self._current_tab = "public"
        self._update_tab_buttons("public")
        safe_create_task(self._load_public_files_async(), "load_public_files")
    
    def _show_notifications_tab(self, widget):
        """Switch to notifications tab."""
        print("[FILES] Switching to Notifications tab", flush=True)
        self._tab_container.clear()
        self._tab_container.add(self._notifications_section)
        self._current_tab = "notifications"
        self._update_tab_buttons("notifications")
        safe_create_task(self._load_notifications_async(), "load_notifications")
    
    async def _fetch_location(self):
        """Fetch user's location via IP geolocation."""
        try:
            from shared.client_core.geolocation import get_location_from_ip
            
            loop = asyncio.get_event_loop()
            location = await loop.run_in_executor(None, get_location_from_ip)
            
            self._user_location = location
            if self._location_label:
                if location.is_fallback:
                    self._location_label.text = f"Location: {location.city}, {location.country} (fallback)"
                else:
                    self._location_label.text = f"Location: {location.city}, {location.country}"
            
            print(f"[FILES] User location: {location.lat}, {location.lon}", flush=True)
        except Exception as e:
            print(f"[FILES] Failed to get location: {e}", flush=True)
            if self._location_label:
                self._location_label.text = "Location: Unknown"
    
    # =========================================================================
    # UPLOAD SECTION
    # =========================================================================
    
    def _build_upload_section(self) -> toga.Box:
        """Build the upload section with all options including blur toggle and storage nodes display."""
        section = toga.Box(
            style=Pack(direction=COLUMN, padding=10, flex=1)
        )
        
        header = toga.Label(
            "Upload Digital Asset",
            style=Pack(font_size=16, font_weight="bold", padding=(0, 0, 10, 0))
        )
        section.add(header)
        
        # File selection row
        file_row = toga.Box(style=Pack(direction=ROW, padding=5))
        
        self.selected_file_label = toga.Label(
            "No file selected",
            style=Pack(flex=1, padding=(5, 10, 5, 0))
        )
        file_row.add(self.selected_file_label)
        
        select_btn = toga.Button(
            "Select File",
            on_press=safe_async_handler(self._on_select_file, "select_file"),
            style=Pack(width=100)
        )
        file_row.add(select_btn)
        section.add(file_row)
        
        # Options grid in a compact layout
        options_box = toga.Box(style=Pack(direction=COLUMN, padding=(5, 0, 5, 0)))
        
        # Row 1: Visibility, Price, Duration
        row1 = toga.Box(style=Pack(direction=ROW, padding=3))
        
        # Visibility
        vis_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        vis_box.add(toga.Label("Visibility:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.visibility_select = toga.Selection(
            items=["public", "private"],
            style=Pack(width=90)
        )
        vis_box.add(self.visibility_select)
        row1.add(vis_box)
        
        # Sell Price
        price_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        price_box.add(toga.Label("Sell Price:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.price_input = toga.TextInput(
            placeholder="0 BZT",
            style=Pack(width=80)
        )
        price_box.add(self.price_input)
        row1.add(price_box)
        
        # Storage Duration
        dur_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        dur_box.add(toga.Label("Duration:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.duration_input = toga.Selection(
            items=["3 years", "5 years", "7 years", "10 years"],
            on_change=self._update_cost_estimate,
            style=Pack(width=90)
        )
        dur_box.add(self.duration_input)
        row1.add(dur_box)
        
        # Blur toggle (default True)
        blur_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        blur_box.add(toga.Label("Blur Preview:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.blur_switch = toga.Switch(
            text="",
            value=True,  # Default to True
            style=Pack(width=60)
        )
        blur_box.add(self.blur_switch)
        row1.add(blur_box)

        options_box.add(row1)

        # Row 1b: Tags
        row1b = toga.Box(style=Pack(direction=ROW, padding=3))
        tags_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        tags_box.add(toga.Label("Tags:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.upload_tags_input = toga.TextInput(
            placeholder="e.g. photo, nature, art (comma-separated)",
            style=Pack(flex=1),
        )
        tags_box.add(self.upload_tags_input)
        row1b.add(tags_box)
        options_box.add(row1b)

        # Row 2: Node selection, proximity, network type, node count
        row2 = toga.Box(style=Pack(direction=ROW, padding=3))
        
        # Node selection mode
        node_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        node_box.add(toga.Label("Node Selection:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.node_select = toga.Selection(
            items=["reputation", "proximity", "price", "random"],
            on_change=self._on_node_selection_change,
            style=Pack(width=100)
        )
        node_box.add(self.node_select)
        row2.add(node_box)
        
        # Proximity range
        prox_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        prox_box.add(toga.Label("Max Distance:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.proximity_select = toga.Selection(
            items=["100 km", "500 km", "1000 km", "Any"],
            on_change=self._on_node_selection_change,
            style=Pack(width=90)
        )
        prox_box.add(self.proximity_select)
        row2.add(prox_box)
        
        # Network type
        net_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        net_box.add(toga.Label("Network:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.network_type_select = toga.Selection(
            items=self._get_available_networks(),
            on_change=self._on_node_selection_change,
            style=Pack(width=100)
        )
        net_box.add(self.network_type_select)
        row2.add(net_box)
        
        # Node count
        nc_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        nc_box.add(toga.Label("Nodes:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.node_count_select = toga.Selection(
            items=["1", "2", "3", "4", "5", "6"],
            on_change=self._on_node_selection_change,
            style=Pack(width=50)
        )
        # Default to 3 nodes
        self.node_count_select.value = "3"
        nc_box.add(self.node_count_select)
        row2.add(nc_box)
        
        options_box.add(row2)
        
        # Row 3: User location
        row3 = toga.Box(style=Pack(direction=ROW, padding=3))
        loc_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        self._location_label = toga.Label(
            "Location: Detecting...",
            style=Pack(font_size=10, color="#666666", padding=(12, 0, 0, 0))
        )
        loc_box.add(self._location_label)
        row3.add(loc_box)
        options_box.add(row3)
        section.add(options_box)
        
        # Cost estimate section (compact)
        cost_section = toga.Box(style=Pack(direction=COLUMN, padding=8, background_color="#fff8e1"))
        
        self.cost_label = toga.Label(
            "Select a file to calculate cost",
            style=Pack(font_size=12, color="#666666")
        )
        cost_section.add(self.cost_label)
        
        section.add(cost_section)
        
        # Selected storage nodes display
        storage_nodes_section = toga.Box(style=Pack(direction=COLUMN, padding=8, background_color="#e3f2fd"))
        
        storage_nodes_section.add(toga.Label(
            "Selected Storage Nodes:",
            style=Pack(font_size=12, font_weight="bold", padding=(0, 0, 5, 0))
        ))
        
        self._selected_nodes_label = toga.Label(
            "Nodes will be selected after file is chosen",
            style=Pack(font_size=11, color="#666666")
        )
        storage_nodes_section.add(self._selected_nodes_label)
        
        section.add(storage_nodes_section)
        
        # Storage nodes info
        storage_nodes = self._get_storage_nodes()
        storage_count = len(storage_nodes)
        
        if storage_nodes:
            prices = sorted([n.get("price_per_chunk", 1.0) for n in storage_nodes])
            price_list = ", ".join([f"{p}" for p in prices[:5]])
            if len(prices) > 5:
                price_list += f", ... (+{len(prices)-5} more)"
            nodes_info = toga.Label(
                f"Available: {storage_count} nodes | Prices: {price_list} BZT/chunk",
                style=Pack(padding=3, color="#666666", font_size=10)
            )
        else:
            nodes_info = toga.Label(
                f"Storage nodes: {storage_count}",
                style=Pack(padding=3, color="#666666", font_size=10)
            )
        section.add(nodes_info)
        
        # Upload button and status
        upload_row = toga.Box(style=Pack(direction=ROW, padding=(8, 0, 0, 0)))
        
        upload_btn = toga.Button(
            "Upload to Network",
            on_press=safe_async_handler(self._on_upload_file, "upload_file"),
            style=Pack(width=150)
        )
        upload_row.add(upload_btn)
        
        self.upload_status = toga.Label(
            "",
            style=Pack(padding=(5, 0, 0, 10), color="#666666", font_size=11)
        )
        upload_row.add(self.upload_status)
        
        section.add(upload_row)
        
        return section
    
    def _get_storage_nodes(self):
        """Get list of storage nodes from consensus."""
        if not self.app.state:
            return []
        return [n for n in self.app.state.active_nodes if n.get("node_type") == "storage"]
    
    def _get_available_networks(self) -> list:
        """Build deduplicated list of network types from active storage nodes."""
        nodes = self._get_storage_nodes()
        networks = set()
        for n in nodes:
            networks.add(n.get("network_type", "default"))
        # Always include "default" at the front
        result = ["default"]
        for net in sorted(networks):
            if net != "default":
                result.append(net)
        return result if result else ["default"]
    
    def _calculate_num_chunks(self, file_size: int) -> int:
        """Calculate number of chunks for a file (100KB chunks)."""
        if file_size <= 0:
            return 0
        return (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    def _calculate_storage_cost(self) -> tuple:
        """Calculate storage cost based on current options.

        Mirrors the actual per-node cost formula used by
        ``client.create_upload_transaction()`` so the estimate shown
        in the UI matches the on-chain amount.
        """
        if not self.selected_file_size:
            return 0, "No file selected", 0

        num_chunks = self._calculate_num_chunks(self.selected_file_size)

        duration_str = self.duration_input.value if self.duration_input else "5 years"
        duration = int(duration_str.split()[0])

        node_mode = self.node_select.value if self.node_select else "reputation"
        network_type = (
            self.network_type_select.value
            if hasattr(self, "network_type_select") and self.network_type_select
            else "default"
        )
        node_count = (
            int(self.node_count_select.value)
            if hasattr(self, "node_count_select") and self.node_count_select
            else 3
        )

        # Parse proximity filter
        proximity_str = (
            self.proximity_select.value if self.proximity_select else "Any"
        )
        max_distance = None
        if proximity_str != "Any":
            try:
                max_distance = int(proximity_str.split()[0])
            except (ValueError, IndexError):
                pass

        # Select the same nodes the upload will use
        selected_nodes = []
        if self.app.client:
            user_lat = self._user_location.lat if self._user_location else None
            user_lon = self._user_location.lon if self._user_location else None
            try:
                selected_nodes = self.app.client._select_storage_nodes(
                    node_selection=node_mode,
                    user_lat=user_lat,
                    user_lon=user_lon,
                    max_distance_km=max_distance,
                    count=node_count,
                    network_type=network_type,
                )
            except Exception:
                pass

        if not selected_nodes:
            selected_nodes = self._get_storage_nodes()

        if not selected_nodes:
            price_per_chunk = 1.0
            cost = num_chunks * price_per_chunk * duration
            breakdown = f"{num_chunks} chunks × {price_per_chunk:.1f} BZT × {duration} yr = {cost:.2f} BZT"
            return cost, breakdown, price_per_chunk

        # Distribute chunks round-robin (same as client.create_upload_transaction)
        node_chunk_count: dict = {}
        for i in range(num_chunks):
            nid = selected_nodes[i % len(selected_nodes)].get("node_id", f"node_{i}")
            node_chunk_count[nid] = node_chunk_count.get(nid, 0) + 1

        node_price_map = {
            n.get("node_id"): n.get("price_per_chunk", 1.0) for n in selected_nodes
        }

        cost = 0.0
        for nid, count in node_chunk_count.items():
            price = node_price_map.get(nid, 1.0)
            cost += count * price * duration

        avg_price = cost / (num_chunks * duration) if num_chunks else 0
        breakdown = (
            f"{num_chunks} chunks across {len(selected_nodes)} nodes "
            f"× {duration} yr = {cost:.2f} BZT (avg {avg_price:.2f}/chunk)"
        )

        return cost, breakdown, avg_price
    
    def _update_cost_estimate(self, widget=None):
        """Update the cost estimate display."""
        if not self.cost_label:
            return
        
        cost, breakdown, _ = self._calculate_storage_cost()
        
        if cost > 0:
            self.cost_label.text = f"Cost: {cost:.2f} BZT ({breakdown})"
        else:
            self.cost_label.text = "Select a file to calculate cost"
        
        # Update selected storage nodes display
        self._update_selected_nodes_display()
    
    def _update_selected_nodes_display(self):
        """Update the display of selected storage nodes."""
        if not self._selected_nodes_label or not self.selected_file_size:
            return
        
        node_mode = self.node_select.value if self.node_select else "reputation"
        network_type = self.network_type_select.value if hasattr(self, 'network_type_select') and self.network_type_select else "default"
        node_count = int(self.node_count_select.value) if hasattr(self, 'node_count_select') and self.node_count_select else 3
        
        # Get user location
        user_lat = self._user_location.lat if self._user_location else None
        user_lon = self._user_location.lon if self._user_location else None
        
        # Get max distance
        proximity_str = self.proximity_select.value if self.proximity_select else "Any"
        max_distance = None
        if proximity_str != "Any":
            max_distance = int(proximity_str.split()[0])
        
        # Select storage nodes
        if self.app.client:
            selected_nodes = self.app.client._select_storage_nodes(
                node_selection=node_mode,
                user_lat=user_lat,
                user_lon=user_lon,
                max_distance_km=max_distance,
                count=node_count,
                network_type=network_type,
            )
            
            if selected_nodes:
                node_info_parts = []
                for i, node in enumerate(selected_nodes, 1):
                    nip = node.get("ip", "?")
                    price = node.get("price_per_chunk", 1.0)
                    rep = node.get("reputation", int(node.get("score", 0) * 100))
                    dist = node.get("_distance")

                    # Highlight the criterion that drove selection
                    if node_mode == "price":
                        detail = f"{price:.1f} BZT/chunk, rep {rep}"
                    elif node_mode == "proximity" and dist is not None:
                        detail = f"{dist:.0f} km, {price:.1f} BZT, rep {rep}"
                    elif node_mode == "reputation":
                        detail = f"rep {rep}, {price:.1f} BZT/chunk"
                    else:
                        detail = f"{price:.1f} BZT, rep {rep}"

                    node_info_parts.append(f"{i}. {nip} ({detail})")

                mode_label = node_mode.capitalize()
                self._selected_nodes_label.text = (
                    f"[{mode_label}] " + " | ".join(node_info_parts)
                )
            else:
                self._selected_nodes_label.text = "No nodes match criteria"
        else:
            self._selected_nodes_label.text = "Client not available"
    
    def _on_node_selection_change(self, widget):
        """Handle node selection mode change."""
        self._update_cost_estimate()
    
    async def _on_select_file(self, widget):
        """Handle file selection."""
        print("[FILES] Select File button pressed", flush=True)
        try:
            file_path = await self.app.main_window.dialog(
                toga.OpenFileDialog(
                    title="Select File to Upload",
                    multiple_select=False
                )
            )
            
            if file_path:
                self.selected_file_path = str(file_path)
                filename = os.path.basename(self.selected_file_path)
                self.selected_file_size = os.path.getsize(self.selected_file_path)
                num_chunks = self._calculate_num_chunks(self.selected_file_size)
                
                self.selected_file_label.text = f"{filename} ({self.selected_file_size:,} bytes, {num_chunks} chunks)"
                self._update_cost_estimate()
            else:
                self.selected_file_path = None
                self.selected_file_size = 0
                self.selected_file_label.text = "No file selected"
                self._update_cost_estimate()
                
        except Exception as e:
            print(f"[FILES] Error selecting file: {e}", flush=True)
            self.selected_file_label.text = f"Error: {e}"
    
    async def _on_upload_file(self, widget):
        """Handle file upload with all options."""
        print("[FILES] Upload button pressed", flush=True)
        
        if not self.selected_file_path:
            print("[FILES] No file selected", flush=True)
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file first.")
            )
            return
        
        print(f"[FILES] Selected file: {self.selected_file_path}", flush=True)
        
        storage_nodes = self._get_storage_nodes()
        print(f"[FILES] Storage nodes: {len(storage_nodes) if storage_nodes else 0}", flush=True)
        
        if not self.app.client:
            print("[FILES] No client available", flush=True)
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", "Client not available.")
            )
            return
        
        if not storage_nodes:
            print("[FILES] No storage nodes available", flush=True)
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", "No storage nodes available.")
            )
            return
        
        # Get all options
        visibility = self.visibility_select.value if self.visibility_select else "public"
        
        price_str = self.price_input.value.strip() if self.price_input else "0"
        try:
            sell_price = float(price_str) if price_str else 0.0
        except ValueError:
            sell_price = 0.0
        
        duration_str = self.duration_input.value if self.duration_input else "5 years"
        duration = int(duration_str.split()[0])
        
        node_selection = self.node_select.value if self.node_select else "reputation"
        network_type = self.network_type_select.value if hasattr(self, 'network_type_select') and self.network_type_select else "default"
        node_count = int(self.node_count_select.value) if hasattr(self, 'node_count_select') and self.node_count_select else 3
        
        proximity_str = self.proximity_select.value if self.proximity_select else "Any"
        max_distance = None
        if proximity_str != "Any":
            max_distance = int(proximity_str.split()[0])
        
        # Get blur value from toggle
        blur_value = "blur" if self.blur_switch and self.blur_switch.value else "none"

        # Get tags
        upload_tags = []
        if hasattr(self, 'upload_tags_input') and self.upload_tags_input and self.upload_tags_input.value:
            upload_tags = [t.strip().lower() for t in self.upload_tags_input.value.split(',') if t.strip()]
        
        # Calculate cost and chunks
        num_chunks = self._calculate_num_chunks(self.selected_file_size)
        storage_cost, breakdown, price_per_chunk = self._calculate_storage_cost()
        
        # Get user location
        user_lat = self._user_location.lat if self._user_location else 48.8566
        user_lon = self._user_location.lon if self._user_location else 2.3522
        
        # Confirm upload
        file_name = os.path.basename(self.selected_file_path)
        confirm = await self.app.main_window.dialog(
            toga.QuestionDialog(
                "Confirm Upload",
                f"File: {file_name}\n"
                f"Size: {self.selected_file_size:,} bytes ({num_chunks} chunks)\n"
                f"Duration: {duration} years\n"
                f"Storage Cost: {storage_cost:.2f} BZT\n"
                f"Visibility: {visibility}\n"
                f"Sell Price: {sell_price} BZT\n"
                f"Network: {network_type}\n"
                f"Nodes: {node_count}\n"
                f"Blur Preview: {'Yes' if blur_value == 'blur' else 'No'}\n"
                f"Tags: {', '.join(upload_tags) if upload_tags else 'none'}\n\n"
                "Proceed with upload?"
            )
        )
        
        if not confirm:
            print("[FILES] Upload cancelled by user", flush=True)
            return
        
        print("[FILES] Starting upload...", flush=True)
        self.upload_status.text = f"Uploading {num_chunks} chunk(s)... please wait"
        
        # Force UI update
        await asyncio.sleep(0.1)
        
        try:
            loop = asyncio.get_event_loop()
            
            file_id = str(uuid.uuid4())
            print(f"[FILES] Generated file_id: {file_id}", flush=True)
            
            wallet = self.app.client.get_current_wallet()
            if not wallet:
                print("[FILES] No wallet connected", flush=True)
                raise Exception("No wallet connected")
            
            print(f"[FILES] Wallet: {wallet.address}", flush=True)
            print(f"[FILES] Creating upload transaction (this may take a while)...", flush=True)
            
            # Run in executor to avoid blocking
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.create_upload_transaction(
                    file_path=self.selected_file_path,
                    file_id=file_id,
                    visibility=visibility,
                    price=sell_price,
                    duration=duration,
                    node_selection=node_selection,
                    user_lat=user_lat,
                    user_lon=user_lon,
                    max_distance_km=max_distance,
                    blur_level=blur_value,
                    network_type=network_type,
                    node_count=node_count,
                    tags=upload_tags if upload_tags else None,
                )
            )
            
            print(f"[FILES] Upload result: status={status}, result={result}", flush=True)
            
            if status in (200, 201):
                if upload_tags:
                    print(f"[FILES] Tags included in TX: {upload_tags}", flush=True)
                
                self.upload_status.text = f"✓ Uploaded: {file_name}"
                await self.app.main_window.dialog(
                    toga.InfoDialog(
                        "Upload Successful",
                        f"File: {file_name}\n"
                        f"Chunks: {num_chunks}\n"
                        f"Cost: {storage_cost:.2f} BZT\n"
                        f"File ID: {file_id[:16]}..."
                    )
                )
                
                # Reset
                self.selected_file_path = None
                self.selected_file_size = 0
                self.selected_file_label.text = "No file selected"
                self._update_cost_estimate()
                
                # Refresh files list
                await self._load_files_async()
            else:
                error = result.get('error', result.get('message', 'Unknown error'))
                # Check for chunk failure details
                failed_chunks = result.get("failed_chunks", [])
                
                if failed_chunks:
                    error_msg = (
                        f"Error: {error}\n\n"
                        f"Failed chunks: {failed_chunks}\n"
                        "Some storage nodes may be offline."
                    )
                else:
                    error_msg = f"Error: {error}"
                
                self.upload_status.text = f"✗ Error: {error}"
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Upload Failed", error_msg)
                )
            
        except Exception as e:
            print(f"[FILES] Upload error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            try:
                self.upload_status.text = f"✗ Error: {e}"
            except Exception:
                pass
            try:
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Error", f"Upload failed: {e}")
                )
            except Exception:
                pass
    
    # =========================================================================
    # MY FILES SECTION
    # =========================================================================
    
    def _build_files_section(self) -> toga.Box:
        """Build the files list section with enhanced details."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        
        # Header with refresh button and debug
        header_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        
        header = toga.Label(
            "My Digital Assets",
            style=Pack(font_size=16, font_weight="bold", flex=1)
        )
        header_row.add(header)
        
        # Debug button to test API
        debug_btn = toga.Button(
            "Test API",
            on_press=safe_async_handler(self._on_test_api, "test_api"),
            style=Pack(width=70, padding=(0, 5, 0, 0))
        )
        header_row.add(debug_btn)
        
        refresh_btn = toga.Button(
            "Refresh",
            on_press=self._on_refresh_files,
            style=Pack(width=80)
        )
        header_row.add(refresh_btn)
        
        section.add(header_row)
        
        # Files table with enhanced columns
        self.files_table = toga.Table(
            headings=["File Name", "Size", "Visibility", "Price", "Expiration", "Block", "Status"],
            data=[],
            style=Pack(flex=1),
            on_select=self._on_file_selected,
            on_activate=self._on_file_double_click
        )
        section.add(self.files_table)
        
        # Selected file details panel (with selectable text for copying)
        self._file_details_box = toga.Box(
            style=Pack(direction=COLUMN, padding=10, background_color="#f5f5f5")
        )
        
        # Use SelectableText if available, otherwise fall back to Label
        if SelectableText:
            self._file_details_text = SelectableText(
                text="Select a file to view details",
                height=60,
                font_size=11,
                color="#666666"
            )
            self._file_details_box.add(self._file_details_text)
            self._file_details_label = None  # Track which widget we're using
        else:
            self._file_details_label = toga.Label(
                "Select a file to view details",
                style=Pack(font_size=11, color="#666666")
            )
            self._file_details_box.add(self._file_details_label)
            self._file_details_text = None
        
        section.add(self._file_details_box)
        
        # Action buttons - Row 1
        actions_row = toga.Box(style=Pack(direction=ROW, padding=(10, 0, 0, 0)))
        
        preview_btn = toga.Button(
            "Preview",
            on_press=safe_async_handler(self._on_preview_file, "preview_file"),
            style=Pack(width=80, padding=(0, 5, 0, 0))
        )
        actions_row.add(preview_btn)
        
        download_btn = toga.Button(
            "Download",
            on_press=safe_async_handler(self._on_download_file, "download_file"),
            style=Pack(width=90, padding=(0, 5, 0, 0))
        )
        actions_row.add(download_btn)
        
        self._update_price_btn = toga.Button(
            "Update Price",
            on_press=safe_async_handler(self._on_update_price, "update_price"),
            style=Pack(width=100, padding=(0, 5, 0, 0))
        )
        actions_row.add(self._update_price_btn)
        
        self._toggle_vis_btn = toga.Button(
            "Toggle Visibility",
            on_press=safe_async_handler(self._on_toggle_visibility, "toggle_visibility"),
            style=Pack(width=120, padding=(0, 5, 0, 0))
        )
        actions_row.add(self._toggle_vis_btn)

        self._edit_tags_btn = toga.Button(
            "Edit Tags",
            on_press=safe_async_handler(self._on_edit_tags, "edit_tags"),
            style=Pack(width=80, padding=(0, 5, 0, 0))
        )
        actions_row.add(self._edit_tags_btn)
        
        section.add(actions_row)
        
        # Action buttons - Row 2 (Ownership)
        actions_row2 = toga.Box(style=Pack(direction=ROW, padding=(5, 0, 0, 0)))
        
        self._transfer_btn = toga.Button(
            "Transfer Ownership",
            on_press=safe_async_handler(self._on_transfer_ownership, "transfer_ownership"),
            style=Pack(width=140, padding=(0, 5, 0, 0), background_color="#ff9800")
        )
        actions_row2.add(self._transfer_btn)
        
        self._lightning_btn = toga.Button(
            "Lightning Transfer",
            on_press=safe_async_handler(self._on_lightning_transfer, "lightning_transfer"),
            style=Pack(width=140, padding=(0, 5, 0, 0), background_color="#f44336")
        )
        actions_row2.add(self._lightning_btn)
        
        section.add(actions_row2)
        
        # Load files asynchronously - removed from build, will load on tab switch
        # safe_create_task(self._load_files_async(), "initial_load_files")
        
        return section
    
    def _on_refresh_files(self, widget):
        """Refresh the files list."""
        print("[FILES] Refresh button pressed", flush=True)
        safe_create_task(self._load_files_async(), "refresh_files")
    
    async def _on_test_api(self, widget):
        """Test API connection and show diagnostic info."""
        print("[FILES] Test API button pressed", flush=True)
        if not self.app.client:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", "Client not available")
            )
            return
        
        wallet = self.app.client.get_current_wallet()
        chain_nodes = self.app.client.get_chain_nodes()
        
        # Build diagnostic info
        diag = []
        diag.append(f"Wallet: {wallet.address if wallet else 'Not connected'}")
        diag.append(f"Chain nodes: {len(chain_nodes)}")
        
        if chain_nodes:
            for i, node in enumerate(chain_nodes[:3]):
                diag.append(f"  Node {i+1}: {node.get('ip', 'unknown')}")
        
        # Try to call API directly
        try:
            loop = asyncio.get_event_loop()
            
            # Get blockchain info first
            info_result, info_status = await loop.run_in_executor(
                None, self.app.client.get_blockchain_info
            )
            diag.append(f"\nBlockchain API: status {info_status}")
            if info_status == 200:
                diag.append(f"  Height: {info_result.get('height', 'N/A')}")
            else:
                diag.append(f"  Error: {info_result.get('error', 'Unknown')}")
            
            # Try uploads endpoint
            if wallet:
                uploads = await loop.run_in_executor(
                    None, self.app.client.get_user_uploads
                )
                diag.append(f"\nUploads found: {len(uploads) if uploads else 0}")
                if uploads:
                    for u in uploads[:3]:
                        diag.append(f"  - {u.get('file_name', 'Unknown')}")
        except Exception as e:
            diag.append(f"\nAPI Error: {e}")
        
        await self.app.main_window.dialog(
            toga.InfoDialog("API Diagnostics", "\n".join(diag))
        )
    
    def _on_file_selected(self, widget):
        """Handle file selection in table - show details."""
        try:
            if not self.files_table:
                return
            
            # Access selection in a try block - it can throw if data was refreshed
            try:
                selection = self.files_table.selection
                if not selection:
                    return
            except (ValueError, IndexError):
                # Row was invalidated by data refresh
                return
            
            # Find the selected file data by matching file_name
            selected_row = selection
            if selected_row and hasattr(selected_row, 'file_name'):
                # Match by file_name attribute from the row
                row_file_name = selected_row.file_name
                for file_data in self._my_files_data:
                    file_name = file_data.get("file_name", "")[:25]
                    if file_name == row_file_name or file_name.startswith(row_file_name.replace("...", "")):
                        self._show_file_details(file_data)
                        # Check if status column indicates transfer pending
                        is_locked = (
                            hasattr(selected_row, 'status')
                            and "Transfer Pending" in str(getattr(selected_row, 'status', ''))
                        )
                        self._set_transfer_lock_ui(is_locked)
                        return
        except Exception as e:
            # Silently ignore selection errors (can happen during data refresh)
            pass

    def _set_transfer_lock_ui(self, locked: bool):
        """Enable/disable asset action buttons based on transfer lock state.

        Args:
            locked: True if the asset has a pending ownership transfer
        """
        for btn in (
            self._update_price_btn,
            self._toggle_vis_btn,
            self._edit_tags_btn,
            self._transfer_btn,
            self._lightning_btn,
        ):
            if btn is not None:
                btn.enabled = not locked

    def _is_selected_file_locked(self) -> bool:
        """Check if the selected file row has a transfer-pending status."""
        try:
            sel = self.files_table.selection if self.files_table else None
            if sel and hasattr(sel, 'status'):
                return "Transfer Pending" in str(getattr(sel, 'status', ''))
        except Exception:
            pass
        return False
    
    def _on_file_double_click(self, widget, row):
        """Handle double-click to preview file."""
        safe_create_task(self._on_preview_file(widget), "preview_on_double_click")
    
    def _show_file_details(self, file_data: dict):
        """Show detailed information about a file (selectable text)."""
        file_id = file_data.get("file_id", "N/A")
        tx_hash = file_data.get("tx_hash", "N/A")
        block_height = file_data.get("block_height", "N/A")
        chunk_locations = file_data.get("chunk_locations", {})
        expiration = file_data.get("expiration_date", "N/A")
        guardian_dam = file_data.get("guardian_dam_id", "N/A")
        
        # Get unique storage nodes
        storage_nodes = set()
        for chunk_id, nodes in chunk_locations.items():
            if isinstance(nodes, list):
                for node in nodes:
                    storage_nodes.add(node[:16] + "..." if len(node) > 16 else node)
        
        nodes_str = ", ".join(list(storage_nodes)[:5])
        if len(storage_nodes) > 5:
            nodes_str += f" (+{len(storage_nodes)-5} more)"
        
        details = (
            f"File ID: {file_id}\n"
            f"TX Hash: {tx_hash}\n"
            f"Block: {block_height} | Expiration: {expiration}\n"
            f"Guardian DAM: {guardian_dam if guardian_dam else 'None'}\n"
            f"Storage Nodes: {nodes_str if nodes_str else 'N/A'}"
        )
        
        # Update the appropriate widget (SelectableText or Label)
        if self._file_details_text:
            self._file_details_text.text = details
        elif self._file_details_label:
            self._file_details_label.text = details
    
    def _show_preview_window(self, title: str, preview_img: toga.Image, subtitle: str = ""):
        """Open a new sub-window to display a preview image.

        Args:
            title: Window title
            preview_img: The toga.Image to display
            subtitle: Optional text below the image
        """
        preview_window = toga.Window(title=title, size=(640, 520))

        content = toga.Box(style=Pack(direction=COLUMN, padding=10, alignment="center"))

        image_view = toga.ImageView(
            image=preview_img,
            style=Pack(flex=1, width=600, height=440)
        )
        content.add(image_view)

        if subtitle:
            label = toga.Label(
                subtitle,
                style=Pack(font_size=11, color="#555555", text_align="center", padding=(8, 0, 0, 0))
            )
            content.add(label)

        close_btn = toga.Button(
            "Close",
            on_press=lambda w: preview_window.close(),
            style=Pack(padding=(8, 0, 0, 0), width=100, alignment="center")
        )
        content.add(close_btn)

        preview_window.content = content
        preview_window.show()

    async def _on_preview_file(self, widget):
        """Handle file preview - opens a sub-window with the blur preview image."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to preview.")
            )
            return
        
        # Get selected file
        selected_file = self._get_selected_file()
        if not selected_file:
            return
        
        file_id = selected_file.get("file_id")
        file_name = selected_file.get("file_name", "Unknown")
        
        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.get_asset_preview(file_id)
            )
            
            has_preview = result.get("has_preview", False) if status == 200 else False
            
            if has_preview:
                preview_b64 = result.get("preview_data", "")
                if preview_b64:
                    try:
                        import base64
                        preview_bytes = base64.b64decode(preview_b64)
                        preview_img = toga.Image(data=preview_bytes)
                        
                        w = result.get("preview_width", "?")
                        h = result.get("preview_height", "?")
                        source = result.get("source", "blockchain")
                        
                        self._show_preview_window(
                            title=f"Preview - {file_name}",
                            preview_img=preview_img,
                            subtitle=f"{file_name}  |  {w}x{h}  |  Source: {source}"
                        )
                        return
                    except Exception as pe:
                        print(f"[FILES] Error displaying preview image: {pe}", flush=True)
            
            await self.app.main_window.dialog(
                toga.InfoDialog(
                    "No Preview",
                    f"No blur preview is available for:\n{file_name}\n\n"
                    "This may happen if the file was uploaded before the preview "
                    "feature was enabled, or the file type is not previewable.\n\n"
                    "Supported types: Images (JPEG, PNG, GIF, WebP), PDF"
                )
            )
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed to load preview: {e}")
            )
    
    async def _on_download_file(self, widget):
        """Handle file download."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to download.")
            )
            return
        
        # Get selected file
        selected_file = self._get_selected_file()
        if not selected_file:
            return
        
        file_id = selected_file.get("file_id")
        file_name = selected_file.get("file_name", "downloaded_file")
        
        # Ask for destination folder
        try:
            folder_path = await self.app.main_window.dialog(
                toga.SelectFolderDialog(title="Select Download Location")
            )
            
            if not folder_path:
                return
            
            # Start download
            await self.app.main_window.dialog(
                toga.InfoDialog("Downloading", f"Downloading {file_name}...")
            )
            
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.download_file(file_id, str(folder_path))
            )
            
            if status == 200:
                await self.app.main_window.dialog(
                    toga.InfoDialog(
                        "Download Complete",
                        f"File saved to:\n{result.get('path', folder_path)}"
                    )
                )
            else:
                error = result.get("error", "Unknown error")
                # Check for chunk failure details
                failed_chunks = result.get("failed_chunks", [])
                total_chunks = result.get("total_chunks", 0)
                successful_chunks = result.get("successful_chunks", 0)
                
                if failed_chunks:
                    error_msg = (
                        f"Error: {error}\n\n"
                        f"Failed chunks: {failed_chunks}\n"
                        f"Successful: {successful_chunks}/{total_chunks}\n\n"
                        "Some storage nodes may be offline or banned."
                    )
                else:
                    error_msg = f"Error: {error}"
                
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Download Failed", error_msg)
                )
                
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Download failed: {e}")
            )
    
    async def _on_update_price(self, widget):
        """Handle price update via a sub-window with a proper text input."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to update.")
            )
            return

        if self._is_selected_file_locked():
            await self.app.main_window.dialog(
                toga.InfoDialog("Locked", "This asset has a pending ownership transfer.\nCancel or complete the transfer first.")
            )
            return

        selected_file = self._get_selected_file()
        if not selected_file:
            return

        file_id = selected_file.get("file_id")
        file_name = selected_file.get("file_name", "Unknown")
        current_price = selected_file.get("price", selected_file.get("marketplace_price", 0))

        price_window = toga.Window(title=f"Update Price: {file_name}")
        box = toga.Box(style=Pack(direction=COLUMN, padding=20))

        box.add(toga.Label(
            f"Update Price for: {file_name}",
            style=Pack(font_weight="bold", padding=(0, 0, 10, 0))
        ))
        box.add(toga.Label(
            f"Current Price: {current_price} BZT",
            style=Pack(font_size=11, color="#888888", padding=(0, 0, 10, 0))
        ))

        box.add(toga.Label("New Price (BZT):", style=Pack(padding=(0, 0, 5, 0))))
        price_input = toga.TextInput(
            placeholder=str(current_price),
            style=Pack(width=150, padding=(0, 0, 10, 0))
        )
        box.add(price_input)

        status_label = toga.Label("", style=Pack(padding=(0, 0, 10, 0), color="#666666"))
        box.add(status_label)

        btn_box = toga.Box(style=Pack(direction=ROW))

        async def on_save(widget):
            val = price_input.value.strip()
            if not val:
                status_label.text = "Error: Enter a price"
                return
            try:
                new_price = float(val)
            except ValueError:
                status_label.text = "Error: Invalid number"
                return

            status_label.text = "Updating price..."
            try:
                loop = asyncio.get_event_loop()
                result, status_code = await loop.run_in_executor(
                    None,
                    lambda: self.app.client.update_asset_price(file_id, new_price)
                )
                if status_code == 200:
                    price_window.close()
                    await self.app.main_window.dialog(
                        toga.InfoDialog("Price Updated", f"Price for {file_name} updated to {new_price} BZT")
                    )
                    await self._load_files_async()
                else:
                    error = result.get("error", "Unknown error")
                    status_label.text = f"Error: {error}"
            except Exception as e:
                status_label.text = f"Error: {e}"

        save_btn = toga.Button(
            "Save",
            on_press=safe_async_handler(on_save, "save_price"),
            style=Pack(width=80, padding=(0, 10, 0, 0), background_color="#4CAF50")
        )
        btn_box.add(save_btn)

        cancel_btn = toga.Button("Cancel", on_press=lambda w: price_window.close(), style=Pack(width=80))
        btn_box.add(cancel_btn)

        box.add(btn_box)
        price_window.content = box
        price_window.size = (380, 260)
        price_window.show()
    
    async def _on_edit_tags(self, widget):
        """Edit tags for the selected file via a sub-window."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file first.")
            )
            return

        if self._is_selected_file_locked():
            await self.app.main_window.dialog(
                toga.InfoDialog("Locked", "This asset has a pending ownership transfer.\nCancel or complete the transfer first.")
            )
            return

        selected_file = self._get_selected_file()
        if not selected_file:
            return

        file_id = selected_file.get("file_id")
        file_name = selected_file.get("file_name", "Unknown")

        # Fetch current tags from API (more reliable than cached data)
        current_tags = selected_file.get("tags") or []
        try:
            loop = asyncio.get_event_loop()
            tag_result, tag_status = await loop.run_in_executor(
                None,
                lambda: self.app.client.get_asset_tags(file_id)
            )
            if tag_status == 200:
                current_tags = tag_result.get("tags", [])
        except Exception:
            pass  # Fall back to cached tags

        tag_window = toga.Window(title=f"Edit Tags: {file_name}")
        box = toga.Box(style=Pack(direction=COLUMN, padding=20))

        box.add(toga.Label(
            f"Tags for: {file_name}",
            style=Pack(font_weight="bold", padding=(0, 0, 10, 0))
        ))

        if current_tags:
            box.add(toga.Label(
                f"Current tags: {', '.join(current_tags)}",
                style=Pack(font_size=10, color="#333333", padding=(0, 0, 5, 0))
            ))

        box.add(toga.Label(
            "Enter comma-separated tags (e.g. photo, nature, art).\nLeave empty to remove all tags.",
            style=Pack(font_size=10, color="#888888", padding=(0, 0, 5, 0))
        ))

        tags_input = toga.TextInput(
            value=", ".join(current_tags),
            style=Pack(width=350, padding=(0, 0, 10, 0))
        )
        box.add(tags_input)

        status_label = toga.Label("", style=Pack(padding=(0, 0, 10, 0), color="#666666"))
        box.add(status_label)

        btn_box = toga.Box(style=Pack(direction=ROW))

        async def on_save(widget):
            raw = tags_input.value.strip()
            new_tags = [t.strip().lower() for t in raw.split(',') if t.strip()] if raw else []
            status_label.text = "Saving tags..."

            try:
                loop = asyncio.get_event_loop()
                result, status_code = await loop.run_in_executor(
                    None,
                    lambda: self.app.client.update_asset_tags(file_id, new_tags)
                )

                if status_code == 200:
                    tag_window.close()
                    await self.app.main_window.dialog(
                        toga.InfoDialog("Tags Updated", f"Tags for {file_name}: {', '.join(new_tags) if new_tags else 'none'}")
                    )
                    await self._load_files_async()
                else:
                    error = result.get("error", "Unknown error")
                    status_label.text = f"Error: {error}"
            except Exception as e:
                status_label.text = f"Error: {e}"

        def on_clear(widget):
            tags_input.value = ""

        save_btn = toga.Button(
            "Save",
            on_press=safe_async_handler(on_save, "save_tags"),
            style=Pack(width=80, padding=(0, 10, 0, 0), background_color="#4CAF50")
        )
        btn_box.add(save_btn)

        clear_btn = toga.Button(
            "Clear All",
            on_press=on_clear,
            style=Pack(width=80, padding=(0, 10, 0, 0), background_color="#ff9800")
        )
        btn_box.add(clear_btn)

        cancel_btn = toga.Button("Cancel", on_press=lambda w: tag_window.close(), style=Pack(width=80))
        btn_box.add(cancel_btn)

        box.add(btn_box)
        tag_window.content = box
        tag_window.size = (420, 280)
        tag_window.show()

    async def _on_toggle_visibility(self, widget):
        """Handle visibility toggle - auto-enable blur when going private."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to update.")
            )
            return

        if self._is_selected_file_locked():
            await self.app.main_window.dialog(
                toga.InfoDialog("Locked", "This asset has a pending ownership transfer.\nCancel or complete the transfer first.")
            )
            return

        selected_file = self._get_selected_file()
        if not selected_file:
            return
        
        file_id = selected_file.get("file_id")
        file_name = selected_file.get("file_name", "Unknown")
        current_visibility = selected_file.get("visibility", "private")
        
        # Toggle visibility
        new_visibility = "private" if current_visibility == "public" else "public"
        
        # When going from public to private, blur is automatically enabled
        blur_note = ""
        if new_visibility == "private":
            blur_note = "\n\nNote: Blur preview will be automatically enabled for private files."
        
        confirm = await self.app.main_window.dialog(
            toga.QuestionDialog(
                "Toggle Visibility",
                f"File: {file_name}\n"
                f"Current: {current_visibility}\n"
                f"New: {new_visibility}{blur_note}\n\n"
                f"Proceed?"
            )
        )
        
        if not confirm:
            return
        
        try:
            loop = asyncio.get_event_loop()
            
            # blur=True is automatically set when visibility is "private"
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.update_asset_visibility(file_id, new_visibility, blur=True)
            )
            
            if status == 200:
                await self.app.main_window.dialog(
                    toga.InfoDialog(
                        "Visibility Updated",
                        f"{file_name} is now {new_visibility}"
                    )
                )
                await self._load_files_async()
            else:
                error = result.get("error", "Unknown error")
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Update Failed", f"Error: {error}")
                )
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed to update visibility: {e}")
            )
    
    async def _on_transfer_ownership(self, widget):
        """Handle ownership transfer initiation."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to transfer.")
            )
            return

        if self._is_selected_file_locked():
            await self.app.main_window.dialog(
                toga.InfoDialog("Locked", "This asset already has a pending ownership transfer.\nCancel or complete it first.")
            )
            return

        selected_file = self._get_selected_file()
        if not selected_file:
            return
        
        file_id = selected_file.get("file_id")
        file_name = selected_file.get("file_name", "Unknown")
        current_price = selected_file.get("price", selected_file.get("marketplace_price", 0))
        
        # Check if there's already a pending transfer for this file
        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.get_pending_ownership_requests()
            )
            
            if status == 200:
                # Check outgoing requests (user is the sender/current owner)
                outgoing = result.get("outgoing", [])
                for req in outgoing:
                    if req.get("file_id") == file_id and req.get("status") == "pending":
                        await self.app.main_window.dialog(
                            toga.ErrorDialog(
                                "Transfer Pending",
                                f"This file already has a pending transfer offer.\n\n"
                                f"To: {req.get('new_owner_address', 'Unknown')[:20]}...\n"
                                f"Price: {req.get('asking_price', 'N/A')}\n\n"
                                f"Cancel the existing offer first in the Notifications tab."
                            )
                        )
                        return
                
                # Check incoming requests (someone offered this file to the user)
                incoming = result.get("incoming", [])
                for req in incoming:
                    if req.get("file_id") == file_id and req.get("status") == "pending":
                        await self.app.main_window.dialog(
                            toga.ErrorDialog(
                                "Transfer Pending",
                                f"This file has a pending incoming offer.\n\n"
                                f"From: {req.get('current_owner_address', 'Unknown')[:20]}...\n"
                                f"Price: {req.get('asking_price', 'N/A')}\n\n"
                                f"Accept or reject it first in the Notifications tab."
                            )
                        )
                        return
        except Exception as e:
            print(f"[FILES] Error checking pending transfers: {e}", flush=True)
        
        # Show transfer dialog
        await self._show_transfer_dialog(file_id, file_name, current_price)
    
    async def _show_transfer_dialog(self, file_id: str, file_name: str, current_price):
        """Show ownership transfer dialog with input fields."""
        # Since Toga doesn't have native multi-input dialogs, we'll use a series of dialogs
        # Step 1: Confirm intent
        confirm = await self.app.main_window.dialog(
            toga.QuestionDialog(
                "Transfer Ownership",
                f"Transfer ownership of:\n{file_name}\n\n"
                f"Current price: {current_price} BZT\n\n"
                "You will need to:\n"
                "1. Enter the new owner's wallet address\n"
                "2. Set the asking price\n\n"
                "The new owner will be able to accept or reject the offer.\n"
                "Continue?"
            )
        )
        
        if not confirm:
            return
        
        # Step 2: Show input form using a custom approach
        # For now, we'll use a workaround with environment-based input
        # In a production app, this would be a proper form dialog
        
        # Create a simple input window
        await self._show_transfer_input_window(file_id, file_name, current_price)
    
    async def _show_transfer_input_window(self, file_id: str, file_name: str, current_price):
        """Show transfer input window."""
        # Create a secondary window for input
        transfer_window = toga.Window(title=f"Transfer: {file_name}")
        
        # Input container
        input_box = toga.Box(style=Pack(direction=COLUMN, padding=20))
        
        # Instructions
        input_box.add(toga.Label(
            f"Transfer ownership of:\n{file_name}",
            style=Pack(padding=(0, 0, 15, 0), font_weight="bold")
        ))
        
        # New owner address input
        input_box.add(toga.Label("New Owner Address:", style=Pack(padding=(0, 0, 5, 0))))
        new_owner_input = toga.TextInput(
            placeholder="Enter wallet address (bez...)",
            style=Pack(width=350, padding=(0, 0, 10, 0))
        )
        input_box.add(new_owner_input)
        
        # Price input
        input_box.add(toga.Label("Asking Price (BZT):", style=Pack(padding=(0, 0, 5, 0))))
        price_input = toga.TextInput(
            placeholder=str(current_price),
            style=Pack(width=150, padding=(0, 0, 10, 0))
        )
        input_box.add(price_input)
        
        # Optional message
        input_box.add(toga.Label("Message (optional):", style=Pack(padding=(0, 0, 5, 0))))
        message_input = toga.TextInput(
            placeholder="Message to new owner",
            style=Pack(width=350, padding=(0, 0, 15, 0))
        )
        input_box.add(message_input)
        
        # Status label
        status_label = toga.Label("", style=Pack(padding=(0, 0, 10, 0), color="#666666"))
        input_box.add(status_label)
        
        # Buttons
        button_box = toga.Box(style=Pack(direction=ROW))
        
        async def on_submit(widget):
            new_owner = new_owner_input.value.strip()
            price_str = price_input.value.strip()
            message = message_input.value.strip()
            
            # Validate inputs
            if not new_owner:
                status_label.text = "Error: Please enter a wallet address"
                return
            
            if not new_owner.startswith("bez"):
                status_label.text = "Error: Address should start with 'bez'"
                return
            
            try:
                price = float(price_str) if price_str else float(current_price) if current_price else 0.0
            except ValueError:
                status_label.text = "Error: Invalid price"
                return
            
            status_label.text = "Submitting transfer request..."
            
            try:
                loop = asyncio.get_event_loop()
                result, status = await loop.run_in_executor(
                    None,
                    lambda: self.app.client.initiate_ownership_transfer(
                        file_id=file_id,
                        new_owner_address=new_owner,
                        asking_price=price,
                        message=message
                    )
                )
                
                if status == 200:
                    # Close window immediately
                    transfer_window.close()
                    
                    # Show success dialog
                    tx_hash = result.get("tx_hash", "")[:16] if result.get("tx_hash") else ""
                    await self.app.main_window.dialog(
                        toga.InfoDialog(
                            "Transfer Initiated",
                            f"Ownership transfer request created!\n\n"
                            f"File: {file_name}\n"
                            f"New Owner: {new_owner[:20]}...\n"
                            f"Price: {price} BZT\n"
                            f"TX: {tx_hash}...\n\n"
                            f"The new owner can now accept or reject the transfer.\n"
                            f"Check the Notifications tab for updates."
                        )
                    )
                    
                    # Refresh the files list to show updated status
                    await self._load_files_async()
                    # Also refresh notifications
                    await self._load_notifications_async()
                else:
                    error = result.get("error", "Unknown error")
                    status_label.text = f"Error: {error}"
            except Exception as e:
                status_label.text = f"Error: {e}"
        
        def on_cancel(widget):
            transfer_window.close()
        
        submit_btn = toga.Button(
            "Submit Transfer",
            on_press=safe_async_handler(on_submit, "submit_transfer"),
            style=Pack(width=120, padding=(0, 10, 0, 0), background_color="#4CAF50")
        )
        button_box.add(submit_btn)
        
        cancel_btn = toga.Button(
            "Cancel",
            on_press=on_cancel,
            style=Pack(width=80)
        )
        button_box.add(cancel_btn)
        
        input_box.add(button_box)
        
        transfer_window.content = input_box
        transfer_window.size = (400, 350)
        transfer_window.show()

    # ---- Lightning Transfer (two-party, no secret sharing) ----

    async def _on_lightning_transfer(self, widget):
        """Seller: create a Lightning offer code for the buyer."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to transfer.")
            )
            return

        if self._is_selected_file_locked():
            await self.app.main_window.dialog(
                toga.InfoDialog("Locked", "This asset already has a pending ownership transfer.\nCancel or complete it first.")
            )
            return

        selected_file = self._get_selected_file()
        if not selected_file:
            return

        file_id = selected_file.get("file_id")
        file_name = selected_file.get("file_name", "Unknown")
        current_price = selected_file.get("price", selected_file.get("marketplace_price", 0))

        await self._show_lightning_offer_window(file_id, file_name, current_price)

    async def _show_lightning_offer_window(self, file_id: str, file_name: str, current_price):
        """Seller: create a signed offer and display the offer code for the buyer.

        No buyer secrets (mnemonic / private key) are needed.  The seller
        only needs the buyer's public wallet address.
        """
        lightning_window = toga.Window(title=f"Lightning Offer: {file_name}")

        input_box = toga.Box(style=Pack(direction=COLUMN, padding=20))

        input_box.add(toga.Label(
            "Lightning Offer (Seller)",
            style=Pack(padding=(0, 0, 5, 0), font_weight="bold", font_size=14, color="#f44336")
        ))
        input_box.add(toga.Label(
            "Create a signed offer code. Send it to the buyer who will\n"
            "accept it from their own wallet (no secrets shared).",
            style=Pack(padding=(0, 0, 15, 0), font_size=10, color="#888888")
        ))
        input_box.add(toga.Label(
            f"File: {file_name}",
            style=Pack(padding=(0, 0, 10, 0), font_weight="bold")
        ))

        # Buyer address (public info only)
        input_box.add(toga.Label("Buyer Address:", style=Pack(padding=(0, 0, 5, 0))))
        buyer_addr_input = toga.TextInput(
            placeholder="Enter buyer wallet address (bez...)",
            style=Pack(width=400, padding=(0, 0, 10, 0))
        )
        input_box.add(buyer_addr_input)

        # Price
        input_box.add(toga.Label("Price (BZT):", style=Pack(padding=(0, 0, 5, 0))))
        price_input = toga.TextInput(
            placeholder=str(current_price),
            style=Pack(width=150, padding=(0, 0, 10, 0))
        )
        input_box.add(price_input)

        # Message
        input_box.add(toga.Label("Message (optional):", style=Pack(padding=(0, 0, 5, 0))))
        message_input = toga.TextInput(
            placeholder="Optional message",
            style=Pack(width=400, padding=(0, 0, 10, 0))
        )
        input_box.add(message_input)

        # Offer code output (read-only, copyable)
        input_box.add(toga.Label("Offer Code (copy & send to buyer):", style=Pack(padding=(5, 0, 5, 0))))
        offer_output = toga.MultilineTextInput(
            readonly=True,
            style=Pack(width=440, height=80, padding=(0, 0, 10, 0))
        )
        input_box.add(offer_output)

        status_label = toga.Label("", style=Pack(padding=(0, 0, 10, 0), color="#666666"))
        input_box.add(status_label)

        button_box = toga.Box(style=Pack(direction=ROW))

        async def on_create_offer(widget):
            buyer_addr = buyer_addr_input.value.strip()
            price_str = price_input.value.strip()
            message = message_input.value.strip()

            if not buyer_addr or not buyer_addr.startswith("bez"):
                status_label.text = "Error: Invalid buyer address"
                return

            try:
                price = float(price_str) if price_str else float(current_price) if current_price else 0.0
            except ValueError:
                status_label.text = "Error: Invalid price"
                return

            status_label.text = "Creating signed offer..."

            try:
                import json as _json
                loop = asyncio.get_event_loop()
                offer, status_code = await loop.run_in_executor(
                    None,
                    lambda: self.app.client.lightning_create_offer(
                        file_id=file_id,
                        buyer_address=buyer_addr,
                        asking_price=price,
                        message=message,
                    )
                )

                if status_code == 200:
                    offer_json = _json.dumps(offer)
                    offer_output.value = offer_json
                    status_label.text = (
                        f"Offer created! Copy the code above and send it to the buyer.\n"
                        f"The buyer pastes it into 'Accept Lightning Offer' in their client."
                    )
                else:
                    error = offer.get("error", "Unknown error")
                    status_label.text = f"Error: {error}"
            except Exception as e:
                status_label.text = f"Error: {e}"

        def on_close(widget):
            lightning_window.close()

        create_btn = toga.Button(
            "Create Offer",
            on_press=safe_async_handler(on_create_offer, "create_lightning_offer"),
            style=Pack(width=120, padding=(0, 10, 0, 0), background_color="#f44336")
        )
        button_box.add(create_btn)

        close_btn = toga.Button(
            "Close",
            on_press=on_close,
            style=Pack(width=80)
        )
        button_box.add(close_btn)

        input_box.add(button_box)
        lightning_window.content = input_box
        lightning_window.size = (500, 520)
        lightning_window.show()

    async def _on_accept_lightning_offer(self, widget):
        """Buyer: paste a Lightning offer code and accept it with own wallet."""
        accept_window = toga.Window(title="Accept Lightning Offer")

        input_box = toga.Box(style=Pack(direction=COLUMN, padding=20))

        input_box.add(toga.Label(
            "Accept Lightning Offer (Buyer)",
            style=Pack(padding=(0, 0, 5, 0), font_weight="bold", font_size=14, color="#4CAF50")
        ))
        input_box.add(toga.Label(
            "Paste the offer code from the seller below.\n"
            "Your wallet will sign the acceptance -- no secrets leave your device.",
            style=Pack(padding=(0, 0, 15, 0), font_size=10, color="#888888")
        ))

        input_box.add(toga.Label("Offer Code:", style=Pack(padding=(0, 0, 5, 0))))
        offer_input = toga.MultilineTextInput(
            placeholder="Paste the Lightning offer JSON here...",
            style=Pack(width=440, height=100, padding=(0, 0, 10, 0))
        )
        input_box.add(offer_input)

        # Preview area
        preview_label = toga.Label("", style=Pack(padding=(0, 0, 10, 0), font_size=11, color="#333333"))
        input_box.add(preview_label)

        status_label = toga.Label("", style=Pack(padding=(0, 0, 10, 0), color="#666666"))
        input_box.add(status_label)

        button_box = toga.Box(style=Pack(direction=ROW))

        async def on_accept(widget):
            offer_text = offer_input.value.strip()
            if not offer_text:
                status_label.text = "Error: Paste the offer code first"
                return

            try:
                import json as _json
                offer = _json.loads(offer_text)
            except Exception:
                status_label.text = "Error: Invalid JSON offer code"
                return

            if offer.get("type") != "lightning_offer":
                status_label.text = "Error: Not a valid Lightning offer"
                return

            # Show what the buyer is agreeing to
            file_name = offer.get("file_name", "Unknown")
            seller = offer.get("seller", "?")[:20]
            price = offer.get("asking_price", "0 BZT")
            msg = offer.get("message", "")
            expires_at = offer.get("expires_at")

            # Check expiry
            import time as _time
            if expires_at and int(_time.time()) > int(expires_at):
                status_label.text = "Error: This offer has expired"
                preview_label.text = f"File: {file_name}\nSeller: {seller}...\nSTATUS: EXPIRED"
                return

            expiry_str = ""
            if expires_at:
                remaining = int(expires_at) - int(_time.time())
                if remaining > 0:
                    mins = remaining // 60
                    expiry_str = f"\nExpires in: {mins} min"

            preview_label.text = (
                f"File: {file_name}\n"
                f"Seller: {seller}...\n"
                f"Price: {price}"
                f"{'  |  ' + msg if msg else ''}"
                f"{expiry_str}"
            )

            status_label.text = "Signing acceptance with your wallet..."

            try:
                loop = asyncio.get_event_loop()
                result, status_code = await loop.run_in_executor(
                    None,
                    lambda: self.app.client.lightning_accept_offer(offer)
                )

                if status_code == 200:
                    accept_window.close()
                    req_hash = result.get("request_tx_hash", "")[:16]
                    acc_hash = result.get("accept_tx_hash", "")[:16]
                    await self.app.main_window.dialog(
                        toga.InfoDialog(
                            "Lightning Transfer Submitted",
                            f"Bundle submitted successfully!\n\n"
                            f"File: {file_name}\n"
                            f"Seller: {seller}...\n"
                            f"Price: {price}\n"
                            f"Request TX: {req_hash}...\n"
                            f"Accept TX:  {acc_hash}...\n\n"
                            f"Both transactions will be mined in the SAME block.\n"
                            f"Ownership transfer completes in ~5 minutes."
                        )
                    )
                    await self._load_files_async()
                    await self._load_notifications_async()
                else:
                    error = result.get("error", "Unknown error")
                    status_label.text = f"Error: {error}"
            except Exception as e:
                status_label.text = f"Error: {e}"

        def on_close(widget):
            accept_window.close()

        accept_btn = toga.Button(
            "Accept & Submit",
            on_press=safe_async_handler(on_accept, "accept_lightning_offer"),
            style=Pack(width=140, padding=(0, 10, 0, 0), background_color="#4CAF50")
        )
        button_box.add(accept_btn)

        close_btn = toga.Button(
            "Cancel",
            on_press=on_close,
            style=Pack(width=80)
        )
        button_box.add(close_btn)

        input_box.add(button_box)
        accept_window.content = input_box
        accept_window.size = (500, 460)
        accept_window.show()

    def _get_selected_file(self) -> dict:
        """Get the currently selected file data."""
        if not self.files_table or not self._my_files_data:
            return None
        
        try:
            # Safely access selection
            try:
                selection = self.files_table.selection
                if not selection:
                    return None
            except (ValueError, IndexError):
                return None
            
            # Try to find matching file by name (use row attribute if available)
            if hasattr(selection, 'file_name'):
                selected_name = selection.file_name
            else:
                selected_name = selection[0] if hasattr(selection, '__getitem__') else str(selection)
            selected_name = selected_name.replace("...", "")
            
            for file_data in self._my_files_data:
                file_name = file_data.get("file_name", "")
                if file_name.startswith(selected_name) or selected_name.startswith(file_name[:20]):
                    return file_data
            
            # Fall back to index-based lookup
            return self._my_files_data[0] if self._my_files_data else None
            
        except Exception as e:
            print(f"[FILES] Error getting selected file: {e}", flush=True)
            return self._my_files_data[0] if self._my_files_data else None
    
    async def _load_files_async(self):
        """Load files from blockchain asynchronously."""
        if not self.app.client or not self.files_table:
            print("[FILES] Client or table not available", flush=True)
            return
        
        if not self.app.client.is_wallet_connected():
            print("[FILES] Wallet not connected", flush=True)
            return
        
        # Check if chain nodes are available
        chain_nodes = self.app.client.get_chain_nodes()
        if not chain_nodes:
            print("[FILES] No chain nodes available, waiting...", flush=True)
            # Wait for consensus to provide chain nodes
            for _ in range(5):  # Wait up to 5 seconds
                await asyncio.sleep(1)
                chain_nodes = self.app.client.get_chain_nodes()
                if chain_nodes:
                    print(f"[FILES] Chain nodes now available: {len(chain_nodes)}", flush=True)
                    break
            
            if not chain_nodes:
                print("[FILES] Still no chain nodes after waiting", flush=True)
                self.files_table.data.clear()
                self.files_table.data.append([
                    "Error", "No chain nodes", "--", "--", "--", "--", "Wait for network"
                ])
                return
        
        try:
            wallet = self.app.client.get_current_wallet()
            print(f"[FILES] Loading files for wallet: {wallet.address if wallet else 'None'}", flush=True)
            print(f"[FILES] Using {len(chain_nodes)} chain nodes", flush=True)
            
            loop = asyncio.get_event_loop()
            uploads = await loop.run_in_executor(
                None, self.app.client.get_user_uploads
            )
            
            print(f"[FILES] Got {len(uploads) if uploads else 0} uploads from API", flush=True)
            
            self._my_files_data = uploads or []
            self.files_table.data.clear()
            
            if not uploads:
                wallet_addr = wallet.address if wallet else "unknown"
                self.files_table.data.append([
                    "No files", f"Wallet: {wallet_addr[:20]}...", "--", "--", "--", "--", "Upload a file first"
                ])
                print(f"[FILES] No uploads found for wallet {wallet_addr}", flush=True)
                return
            
            # Fetch pending transfer info to mark files with active transfers
            pending_file_ids = set()
            try:
                pending_result, pending_status = await loop.run_in_executor(
                    None, self.app.client.get_pending_ownership_requests
                )
                if pending_status == 200:
                    for req in pending_result.get("outgoing", []):
                        if req.get("status") == "pending":
                            pending_file_ids.add(req.get("file_id"))
                    for req in pending_result.get("incoming", []):
                        if req.get("status") == "pending":
                            pending_file_ids.add(req.get("file_id"))
            except Exception as pe:
                print(f"[FILES] Error fetching pending transfers: {pe}", flush=True)
            
            for upload in uploads:
                if upload is None:
                    continue
                    
                file_name = upload.get("file_name", "Unknown")
                file_size = upload.get("file_size", 0)
                visibility = upload.get("visibility", "private")
                price = upload.get("price", upload.get("marketplace_price", "0"))
                file_id = upload.get("file_id", "")
                
                # Calculate expiration date
                storage_duration = upload.get("storage_duration", 5)
                created_at = upload.get("created_at", "")
                if created_at:
                    try:
                        created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        expiration = created_date + timedelta(days=storage_duration * 365)
                        expiration_str = expiration.strftime("%Y-%m-%d")
                    except:
                        expiration_str = f"+{storage_duration}y"
                else:
                    expiration_str = f"+{storage_duration}y"
                
                block_height = upload.get("block_height", "Pending")
                status = upload.get("status", "confirmed")
                
                # Status display with transfer indicator
                if file_id in pending_file_ids:
                    status_display = "🔒 Transfer Pending"
                elif status == "confirmed":
                    status_display = "✓ Confirmed"
                else:
                    status_display = "⏳ Pending"
                
                self.files_table.data.append([
                    file_name[:25] + "..." if len(file_name) > 25 else file_name,
                    f"{file_size:,}" if file_size else "--",
                    visibility,
                    f"{price}" if price and price != "0" else "Free",
                    expiration_str,
                    str(block_height) if block_height else "Pending",
                    status_display
                ])
                
        except Exception as e:
            print(f"[FILES] Error loading files: {e}", flush=True)
            import traceback
            traceback.print_exc()
            if self.files_table:
                self.files_table.data.clear()
                self.files_table.data.append([
                    "Error", str(e)[:30], "--", "--", "--", "--", "Check console"
                ])
    
    # =========================================================================
    # PUBLIC FILES SECTION
    # =========================================================================
    
    def _build_public_section(self) -> toga.Box:
        """Build the public files marketplace section with search, tags, preview."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))

        # Header
        header = toga.Label(
            "Public Digital Assets Marketplace",
            style=Pack(font_size=16, font_weight="bold", padding=(0, 0, 10, 0))
        )
        section.add(header)

        # Search row
        search_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 5, 0)))

        self._public_search_input = toga.TextInput(
            placeholder="Search by file name...",
            style=Pack(flex=1, padding=(0, 5, 0, 0))
        )
        search_row.add(self._public_search_input)

        search_btn = toga.Button(
            "Search",
            on_press=self._on_search_public,
            style=Pack(width=80, padding=(0, 5, 0, 0))
        )
        search_row.add(search_btn)

        refresh_btn = toga.Button(
            "Refresh",
            on_press=self._on_refresh_public,
            style=Pack(width=80)
        )
        search_row.add(refresh_btn)

        section.add(search_row)

        # Filter row: tags + price range
        filter_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))

        filter_row.add(toga.Label("Tags:", style=Pack(padding=(5, 5, 0, 0))))
        self._tags_search_input = toga.TextInput(
            placeholder="e.g. photo, art, doc",
            style=Pack(width=150, padding=(0, 10, 0, 0))
        )
        filter_row.add(self._tags_search_input)

        filter_row.add(toga.Label("Min:", style=Pack(padding=(5, 5, 0, 0))))
        self._min_price_input = toga.TextInput(
            placeholder="0",
            style=Pack(width=50, padding=(0, 5, 0, 0))
        )
        filter_row.add(self._min_price_input)

        filter_row.add(toga.Label("Max:", style=Pack(padding=(5, 5, 0, 0))))
        self._max_price_input = toga.TextInput(
            placeholder="∞",
            style=Pack(width=50)
        )
        filter_row.add(self._max_price_input)

        section.add(filter_row)

        # Public files table
        self.public_files_table = toga.Table(
            headings=["File Name", "Owner", "Price (BZT)", "Tags", "Size"],
            data=[],
            style=Pack(flex=1),
            on_select=self._on_public_file_selected,
            on_activate=self._on_public_file_double_click,
        )
        section.add(self.public_files_table)

        # Asset details panel (with selectable text for copying)
        self._public_details_box = toga.Box(
            style=Pack(direction=COLUMN, padding=10, background_color="#f5f5f5")
        )

        if SelectableText:
            self._public_details_text = SelectableText(
                text="Select an asset to view details",
                height=60,
                font_size=11,
                color="#666666",
            )
            self._public_details_box.add(self._public_details_text)
            self._public_details_label = None
        else:
            self._public_details_label = toga.Label(
                "Select an asset to view details",
                style=Pack(font_size=11, color="#666666"),
            )
            self._public_details_box.add(self._public_details_label)
            self._public_details_text = None

        section.add(self._public_details_box)

        # Action buttons
        actions_row = toga.Box(style=Pack(direction=ROW, padding=(10, 0, 0, 0)))

        preview_btn = toga.Button(
            "View Preview",
            on_press=safe_async_handler(self._on_preview_public_file, "preview_public"),
            style=Pack(width=100, padding=(0, 5, 0, 0))
        )
        actions_row.add(preview_btn)

        history_btn = toga.Button(
            "View History",
            on_press=safe_async_handler(self._on_view_history, "view_history"),
            style=Pack(width=100, padding=(0, 5, 0, 0))
        )
        actions_row.add(history_btn)

        request_btn = toga.Button(
            "Request Ownership",
            on_press=safe_async_handler(self._on_request_ownership, "request_ownership"),
            style=Pack(width=140, padding=(0, 5, 0, 0), background_color="#2196F3")
        )
        actions_row.add(request_btn)

        section.add(actions_row)

        return section
    
    def _on_search_public(self, widget):
        """Search public files."""
        print("[FILES] Search public files", flush=True)
        safe_create_task(self._load_public_files_async(), "search_public")
    
    def _on_refresh_public(self, widget):
        """Refresh public files."""
        print("[FILES] Refresh public files", flush=True)
        safe_create_task(self._load_public_files_async(), "refresh_public")
    
    def _on_public_file_selected(self, widget):
        """Handle public file selection."""
        try:
            if not self.public_files_table:
                return
            
            try:
                selection = self.public_files_table.selection
                if not selection:
                    return
            except (ValueError, IndexError):
                return
            
            selected_file = self._get_selected_public_file()
            if selected_file:
                self._show_public_file_details(selected_file)
        except Exception:
            pass
    
    def _on_public_file_double_click(self, widget, row):
        """Handle double-click on public file - show preview."""
        safe_create_task(self._on_preview_public_file(widget), "preview_public_double_click")
    
    def _show_public_file_details(self, file_data: dict):
        """Show public file details (selectable text)."""
        file_id = file_data.get("file_id", "N/A")
        owner = file_data.get("owner_address", "N/A")
        price = file_data.get("marketplace_price", file_data.get("price", "0"))
        num_chunks = file_data.get("num_chunks", 0)
        file_size = file_data.get("file_size", 0)
        tags = file_data.get("tags") or []
        encrypted = file_data.get("encrypted", False)

        tags_str = ", ".join(tags) if tags else "none"
        enc_str = "Yes" if encrypted else "No"

        details = (
            f"File ID: {file_id}\n"
            f"Owner: {owner}\n"
            f"Price: {price} BZT | Size: {file_size:,} bytes"
            f"{f' ({num_chunks} chunks)' if num_chunks else ''}\n"
            f"Tags: {tags_str} | Encrypted: {enc_str}"
        )
        
        # Update the appropriate widget (SelectableText or Label)
        if hasattr(self, '_public_details_text') and self._public_details_text:
            self._public_details_text.text = details
        elif self._public_details_label:
            self._public_details_label.text = details
    
    def _get_selected_public_file(self) -> dict:
        """Get the selected public file data."""
        if not self.public_files_table:
            return None
        
        try:
            # Safely access selection
            try:
                selection = self.public_files_table.selection
                if not selection:
                    return None
            except (ValueError, IndexError):
                return None
            
            # Get name from row attribute if available
            if hasattr(selection, 'file_name'):
                selected_name = selection.file_name
            else:
                selected_name = selection[0] if hasattr(selection, '__getitem__') else str(selection)
            selected_name = selected_name.replace("...", "")
            
            for file_data in self._public_files_data:
                file_name = file_data.get("file_name", "")
                if file_name.startswith(selected_name) or selected_name.startswith(file_name[:20]):
                    return file_data
            
            return self._public_files_data[0] if self._public_files_data else None
        except:
            return self._public_files_data[0] if self._public_files_data else None
    
    async def _on_preview_public_file(self, widget):
        """Preview a public file -- shows blur preview in a sub-window."""
        selected = self._get_selected_public_file()
        if not selected:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to preview.")
            )
            return

        file_id = selected.get("file_id")
        file_name = selected.get("file_name", "Unknown")
        price = selected.get("marketplace_price", selected.get("price", 0))
        owner = selected.get("owner_address", selected.get("owner", "Unknown"))
        tags = selected.get("tags") or []

        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.get_asset_preview(file_id)
            )

            has_preview = result.get("has_preview", False) if status == 200 else False

            if has_preview:
                preview_b64 = result.get("preview_data", "")
                if preview_b64:
                    try:
                        import base64
                        preview_bytes = base64.b64decode(preview_b64)
                        preview_img = toga.Image(data=preview_bytes)
                        tags_str = ", ".join(tags) if tags else ""
                        subtitle = (
                            f"{file_name}  |  Price: {price} BZT  |  "
                            f"Owner: {str(owner)[:20]}..."
                        )
                        if tags_str:
                            subtitle += f"  |  Tags: {tags_str}"
                        self._show_preview_window(
                            title=f"Marketplace Preview - {file_name}",
                            preview_img=preview_img,
                            subtitle=subtitle,
                        )
                        return
                    except Exception as pe:
                        print(f"[FILES] Error displaying marketplace preview: {pe}", flush=True)

            await self.app.main_window.dialog(
                toga.InfoDialog(
                    f"No Preview: {file_name}",
                    f"No blur preview available for this asset.\n\n"
                    f"Price: {price} BZT\n"
                    f"Owner: {str(owner)[:25]}...\n\n"
                    f"You can still request ownership."
                )
            )
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed to load preview: {e}")
            )
    
    async def _on_view_history(self, widget):
        """View detailed ownership/change history of a public file."""
        selected = self._get_selected_public_file()
        if not selected:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to view history.")
            )
            return
        
        file_id = selected.get("file_id")
        file_name = selected.get("file_name", "Unknown")
        
        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.get_asset_history(file_id)
            )
            
            if status == 200:
                history = result.get("history", [])
                if history:
                    lines = []
                    for h in history[:15]:
                        event = h.get("event_type", "unknown")
                        block = h.get("block_height", "?")
                        ts = h.get("timestamp", "")[:19]
                        details = h.get("details", {})
                        tx_hash = h.get("tx_hash", "")[:12]
                        
                        # Format event-specific details
                        if event == "upload":
                            desc = f"Uploaded: {details.get('file_name', file_name)}"
                            extra = f"Size: {details.get('file_size', '?')} bytes"
                        elif event == "update_price":
                            old_p = details.get("old_price", "?")
                            new_p = details.get("new_price", "?")
                            desc = f"Price changed: {old_p} → {new_p} BZT"
                            extra = ""
                        elif event == "update_visibility":
                            old_v = details.get("old_visibility", "?")
                            new_v = details.get("new_visibility", "?")
                            desc = f"Visibility: {old_v} → {new_v}"
                            extra = ""
                        elif event == "ownership_transfer":
                            from_a = details.get("from_address", "?")[:16]
                            to_a = details.get("to_address", "?")[:16]
                            price = details.get("price", "0")
                            desc = f"Ownership: {from_a}... → {to_a}..."
                            extra = f"Price: {price} BZT"
                        elif event == "update_tags":
                            desc = f"Tags updated"
                            extra = f"Tags: {', '.join(details.get('tags', []))}" if details.get("tags") else ""
                        else:
                            desc = event.replace("_", " ").title()
                            extra = ""
                        
                        line = f"Block #{block}  |  {desc}"
                        if extra:
                            line += f"\n           {extra}"
                        line += f"\n           TX: {tx_hash}...  |  {ts}"
                        lines.append(line)
                    
                    history_text = "\n\n".join(lines)
                else:
                    history_text = "No history available"
                
                await self.app.main_window.dialog(
                    toga.InfoDialog(
                        f"History: {file_name}",
                        history_text
                    )
                )
            else:
                await self.app.main_window.dialog(
                    toga.InfoDialog("No History", "No history available for this file.")
                )
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed to load history: {e}")
            )
    
    async def _on_request_ownership(self, widget):
        """Buyer-initiated ownership request for a public marketplace asset."""
        selected = self._get_selected_public_file()
        if not selected:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to request.")
            )
            return

        file_id = selected.get("file_id")
        file_name = selected.get("file_name", "Unknown")
        price = selected.get("marketplace_price", selected.get("price", "0"))
        owner = selected.get("owner_address", selected.get("owner", "Unknown"))

        # Don't allow requesting own files
        if self.app.client and self.app.client.get_current_wallet():
            my_address = self.app.client.get_current_wallet().address
            if owner == my_address:
                await self.app.main_window.dialog(
                    toga.InfoDialog("Own File", "You already own this file.")
                )
                return

        # Confirm purchase
        confirmed = await self.app.main_window.dialog(
            toga.QuestionDialog(
                "Confirm Purchase Request",
                f"Request ownership of:\n\n"
                f"File: {file_name}\n"
                f"Price: {price} BZT\n"
                f"Current owner: {str(owner)[:25]}...\n\n"
                f"An ownership_request transaction will be sent.\n"
                f"The owner will see it in their notifications and\n"
                f"can accept or reject your request.\n\n"
                f"Proceed?"
            )
        )

        if not confirmed:
            return

        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.create_ownership_request_from_marketplace(
                    file_id=file_id,
                    message=f"Marketplace purchase request for {file_name}",
                )
            )

            if status == 200:
                tx_hash = result.get("tx_hash", "")[:16]
                await self.app.main_window.dialog(
                    toga.InfoDialog(
                        "Request Sent",
                        f"Ownership request submitted!\n\n"
                        f"File: {file_name}\n"
                        f"Price: {price} BZT\n"
                        f"TX: {tx_hash}...\n\n"
                        f"The owner will receive your request and can\n"
                        f"accept or reject it from their notifications."
                    )
                )
            else:
                error = result.get("error", "Unknown error")
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Request Failed", f"Error: {error}")
                )
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed to send request: {e}")
            )
    
    async def _load_public_files_async(self):
        """Load public files from the marketplace (via PostgreSQL)."""
        if not self.app.client or not self.public_files_table:
            return

        try:
            query = self._public_search_input.value if self._public_search_input else ""

            # Parse tags
            tags = None
            if hasattr(self, '_tags_search_input') and self._tags_search_input and self._tags_search_input.value:
                raw = self._tags_search_input.value.strip()
                tags = [t.strip().lower() for t in raw.split(',') if t.strip()]

            min_price = None
            max_price = None

            if self._min_price_input and self._min_price_input.value:
                try:
                    min_price = float(self._min_price_input.value)
                except (ValueError, TypeError):
                    pass

            if self._max_price_input and self._max_price_input.value:
                try:
                    max_price = float(self._max_price_input.value)
                except (ValueError, TypeError):
                    pass

            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.search_public_assets(
                    query=query,
                    tags=tags,
                    min_price=min_price,
                    max_price=max_price,
                )
            )

            self.public_files_table.data.clear()

            if status == 200:
                assets = result.get("assets", [])
                self._public_files_data = assets

                if not assets:
                    self.public_files_table.data.append([
                        "--", "No public files found", "--", "--", "--"
                    ])
                    return

                for asset in assets:
                    file_name = asset.get("file_name", "Unknown")
                    owner = asset.get("owner_address", "Unknown")
                    price = asset.get("marketplace_price", asset.get("price", "0"))
                    asset_tags = asset.get("tags") or []
                    file_size = asset.get("file_size", 0)

                    tags_display = ", ".join(asset_tags[:3])
                    if len(asset_tags) > 3:
                        tags_display += "..."

                    self.public_files_table.data.append([
                        file_name[:25] + "..." if len(file_name) > 25 else file_name,
                        owner[:12] + "..." if len(owner) > 12 else owner,
                        f"{price}" if price else "Free",
                        tags_display if tags_display else "--",
                        f"{file_size:,}" if file_size else "--",
                    ])
            else:
                self._public_files_data = []
                self.public_files_table.data.append([
                    "--", "Error loading public files", "--", "--", "--"
                ])

        except Exception as e:
            print(f"[FILES] Error loading public files: {e}", flush=True)
            self._public_files_data = []
    
    # =========================================================================
    # NOTIFICATIONS SECTION
    # =========================================================================
    
    def _build_notifications_section(self) -> toga.Box:
        """Build the notifications section for ownership requests/responses."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        
        # Header
        header_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        
        header = toga.Label(
            "Ownership Requests & Notifications",
            style=Pack(font_size=16, font_weight="bold", flex=1)
        )
        header_row.add(header)
        
        refresh_btn = toga.Button(
            "Refresh",
            on_press=self._on_refresh_notifications,
            style=Pack(width=80)
        )
        header_row.add(refresh_btn)

        lightning_accept_btn = toga.Button(
            "Accept Lightning Offer",
            on_press=safe_async_handler(self._on_accept_lightning_offer, "accept_lightning"),
            style=Pack(width=180, padding=(0, 0, 0, 10), background_color="#4CAF50")
        )
        header_row.add(lightning_accept_btn)
        
        section.add(header_row)
        
        # Incoming requests section
        section.add(toga.Label(
            "Incoming Offers (Files offered to you)",
            style=Pack(font_size=14, font_weight="bold", padding=(10, 0, 5, 0))
        ))
        
        self._incoming_table = toga.Table(
            headings=["File", "From", "Price", "Date", "Status"],
            data=[],
            style=Pack(height=150),
            on_select=self._on_incoming_selected
        )
        section.add(self._incoming_table)
        
        # Actions for incoming requests
        incoming_actions = toga.Box(style=Pack(direction=ROW, padding=(5, 0, 10, 0)))
        
        preview_offer_btn = toga.Button(
            "Preview",
            on_press=safe_async_handler(self._on_preview_incoming, "preview_incoming"),
            style=Pack(width=80, padding=(0, 5, 0, 0))
        )
        incoming_actions.add(preview_offer_btn)
        
        accept_btn = toga.Button(
            "Accept",
            on_press=safe_async_handler(self._on_accept_request, "accept_request"),
            style=Pack(width=80, padding=(0, 5, 0, 0), background_color="#4CAF50")
        )
        incoming_actions.add(accept_btn)
        
        reject_btn = toga.Button(
            "Reject",
            on_press=safe_async_handler(self._on_reject_request, "reject_request"),
            style=Pack(width=80, padding=(0, 5, 0, 0), background_color="#f44336")
        )
        incoming_actions.add(reject_btn)
        
        section.add(incoming_actions)
        
        # Outgoing requests section (transfers you initiated)
        section.add(toga.Label(
            "Outgoing Requests (Transfer offers you've created)",
            style=Pack(font_size=14, font_weight="bold", padding=(10, 0, 5, 0))
        ))
        
        self._outgoing_table = toga.Table(
            headings=["File", "To", "Price", "Date", "Status"],
            data=[],
            style=Pack(height=150),
            on_select=self._on_outgoing_selected
        )
        section.add(self._outgoing_table)
        
        # Actions for outgoing requests
        outgoing_actions = toga.Box(style=Pack(direction=ROW, padding=(5, 0, 10, 0)))
        
        cancel_btn = toga.Button(
            "Cancel Request",
            on_press=safe_async_handler(self._on_cancel_request, "cancel_request"),
            style=Pack(width=120, padding=(0, 5, 0, 0), background_color="#ff9800")
        )
        outgoing_actions.add(cancel_btn)
        
        section.add(outgoing_actions)
        
        # Status label
        self._notifications_status = toga.Label(
            "",
            style=Pack(padding=(10, 0, 0, 0), color="#666666")
        )
        section.add(self._notifications_status)
        
        return section
    
    def _on_refresh_notifications(self, widget):
        """Refresh notifications."""
        print("[FILES] Refresh notifications", flush=True)
        safe_create_task(self._load_notifications_async(), "refresh_notifications")
    
    def _on_incoming_selected(self, widget):
        """Handle incoming request selection."""
        pass
    
    async def _on_preview_incoming(self, widget):
        """Load and display the blur preview for the selected incoming offer in a sub-window."""
        request = self._get_selected_incoming_request()
        if not request or not request.get("file_id"):
            await self.app.main_window.dialog(
                toga.InfoDialog("Select Request", "Please select an incoming offer first.")
            )
            return
        
        file_id = request.get("file_id")
        file_name = request.get("file_name", "Unknown")
        current_owner = request.get("current_owner_address", "")
        price = request.get("asking_price", "0")
        message = request.get("message", "")
        
        try:
            img = await self._fetch_preview_image(file_id)
            if img:
                msg_part = f"  |  \"{message}\"" if message else ""
                self._show_preview_window(
                    title=f"Offer Preview - {file_name}",
                    preview_img=img,
                    subtitle=(
                        f"{file_name}  |  From: {current_owner[:24]}...  |  "
                        f"Price: {price} BZT{msg_part}"
                    )
                )
            else:
                await self.app.main_window.dialog(
                    toga.InfoDialog(
                        "No Preview",
                        f"No blur preview available for {file_name}.\n\n"
                        "The file may not be a previewable type (images, PDFs)."
                    )
                )
        except Exception as e:
            print(f"[FILES] Preview load error: {e}", flush=True)
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed to load preview: {e}")
            )
    
    def _on_outgoing_selected(self, widget):
        """Handle outgoing request selection."""
        pass
    
    def _get_selected_incoming_request(self) -> dict:
        """Get the selected incoming request."""
        try:
            if not self._incoming_table:
                return None
            
            try:
                selection = self._incoming_table.selection
                if not selection:
                    return None
            except (ValueError, IndexError):
                return None
            
            incoming = [r for r in self._notifications_data if r.get("type") == "incoming"]
            if not incoming:
                return None
            
            # Try to match by file name from selection
            if hasattr(selection, '__getitem__') or hasattr(selection, 'file'):
                try:
                    sel_file = selection[0] if hasattr(selection, '__getitem__') else getattr(selection, 'file', '')
                    for req in incoming:
                        fname = req.get("file_name", "")
                        display_name = fname[:20] + "..." if len(fname) > 20 else fname
                        if display_name == sel_file:
                            return req
                except:
                    pass
            
            # Fallback: try matching by index
            try:
                idx = list(self._incoming_table.data).index(selection)
                if idx < len(incoming):
                    return incoming[idx]
            except (ValueError, IndexError):
                pass
            
            return incoming[0] if incoming else None
        except:
            pass
        return None
    
    def _get_selected_outgoing_request(self) -> dict:
        """Get the selected outgoing request."""
        try:
            if not self._outgoing_table:
                return None
            
            try:
                selection = self._outgoing_table.selection
                if not selection:
                    return None
            except (ValueError, IndexError):
                return None
            
            outgoing = [r for r in self._notifications_data if r.get("type") == "outgoing"]
            if not outgoing:
                return None
            
            # Try to match by file name from selection
            if hasattr(selection, '__getitem__') or hasattr(selection, 'file'):
                try:
                    sel_file = selection[0] if hasattr(selection, '__getitem__') else getattr(selection, 'file', '')
                    for req in outgoing:
                        fname = req.get("file_name", "")
                        display_name = fname[:20] + "..." if len(fname) > 20 else fname
                        if display_name == sel_file:
                            return req
                except:
                    pass
            
            # Fallback: try matching by index
            try:
                idx = list(self._outgoing_table.data).index(selection)
                if idx < len(outgoing):
                    return outgoing[idx]
            except (ValueError, IndexError):
                pass
            
            return outgoing[0] if outgoing else None
        except:
            pass
        return None
    
    async def _fetch_preview_image(self, file_id: str) -> toga.Image:
        """Fetch the blur preview image for a digital asset.
        
        Args:
            file_id: UUID of the digital asset
            
        Returns:
            toga.Image or None if preview unavailable
        """
        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.get_asset_preview(file_id)
            )
            
            if status == 200 and result.get("has_preview"):
                preview_b64 = result.get("preview_data", "")
                if preview_b64:
                    import base64
                    preview_bytes = base64.b64decode(preview_b64)
                    return toga.Image(data=preview_bytes)
        except Exception as e:
            print(f"[FILES] Error fetching preview: {e}", flush=True)
        
        return None
    
    async def _on_accept_request(self, widget):
        """Accept an incoming ownership request.
        
        Handles both flows:
        - Buyer-initiated: seller approves the purchase (buyer pays)
        - Seller-initiated: buyer accepts the offer (buyer pays)
        """
        request = self._get_selected_incoming_request()
        if not request:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select Request", "Please select a request to accept.")
            )
            return
        
        request_id = request.get("request_id")
        file_id = request.get("file_id")
        file_name = request.get("file_name", "Unknown")
        price_str = request.get("asking_price", "0")
        current_owner = request.get("current_owner_address", "")
        new_owner = request.get("new_owner_address", "")
        my_address = self.app.client.state.CURRENT_WALLET.address if self.app.client.state.CURRENT_WALLET else ""

        # Parse price
        try:
            if isinstance(price_str, str):
                price = float(price_str.replace(" BZT", "").replace("BZT", "").strip())
            else:
                price = float(price_str or 0)
        except Exception:
            price = 0.0

        # Determine if I'm the seller (current_owner) or buyer (new_owner)
        i_am_seller = (current_owner == my_address)
        i_am_buyer = (new_owner == my_address)

        if i_am_buyer and price > 0:
            # Buyer needs to pay -- check balance
            try:
                loop = asyncio.get_event_loop()
                balance_result, balance_status = await loop.run_in_executor(
                    None,
                    lambda: self.app.client.get_wallet_balance()
                )
                if balance_status == 200:
                    current_balance = float(balance_result.get("balance", 0))
                    if current_balance < price:
                        await self.app.main_window.dialog(
                            toga.ErrorDialog(
                                "Insufficient Funds",
                                f"You need {price} BZT to acquire this asset.\n\n"
                                f"Your balance: {current_balance} BZT\n"
                                f"Shortfall: {price - current_balance:.2f} BZT"
                            )
                        )
                        return
            except Exception as e:
                print(f"[FILES] Balance check error: {e}", flush=True)

        if i_am_seller:
            confirm_msg = (
                f"Approve sale of: {file_name}\n\n"
                f"Buyer: {new_owner[:20]}...\n"
                f"Price: {price} BZT\n\n"
                f"The buyer will pay {price} BZT.\n"
                f"The asset will become private for the buyer.\n"
                f"Continue?"
            )
        else:
            confirm_msg = (
                f"Accept ownership of: {file_name}\n\n"
                f"From: {current_owner[:20]}...\n"
                f"Price: {price} BZT\n\n"
                f"You will PAY {price} BZT to acquire this asset.\n"
                f"Continue?"
            )

        confirm = await self.app.main_window.dialog(
            toga.QuestionDialog("Accept Transfer", confirm_msg)
        )

        if not confirm:
            return

        try:
            loop = asyncio.get_event_loop()

            if i_am_seller:
                # Seller approves buyer-initiated request
                result, status = await loop.run_in_executor(
                    None,
                    lambda: self.app.client.seller_accept_ownership_request(
                        request_id, file_id, new_owner, price
                    )
                )
            else:
                # Buyer accepts seller-initiated offer
                result, status = await loop.run_in_executor(
                    None,
                    lambda: self.app.client.accept_ownership_request(request_id, file_id, price)
                )

            if status == 200:
                if i_am_seller:
                    msg = f"Sale approved for: {file_name}\n\nBuyer {new_owner[:20]}... will receive the asset."
                else:
                    msg = f"You are now the owner of: {file_name}\n\nPayment: {price} BZT sent to previous owner."
                await self.app.main_window.dialog(toga.InfoDialog("Transfer Complete", msg))
                await self._load_notifications_async()
                await self._load_files_async()
            else:
                error = result.get("error", "Unknown error")
                await self.app.main_window.dialog(toga.ErrorDialog("Error", f"Failed: {error}"))
        except Exception as e:
            await self.app.main_window.dialog(toga.ErrorDialog("Error", f"Failed: {e}"))
    
    async def _on_reject_request(self, widget):
        """Reject an incoming ownership request (as the NEW owner)."""
        request = self._get_selected_incoming_request()
        if not request:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select Request", "Please select a request to reject.")
            )
            return
        
        request_id = request.get("request_id")
        file_id = request.get("file_id")
        file_name = request.get("file_name", "Unknown")
        
        confirm = await self.app.main_window.dialog(
            toga.QuestionDialog(
                "Reject Transfer",
                f"Reject ownership offer for: {file_name}?\n\n"
                f"The current owner will be notified."
            )
        )
        
        if not confirm:
            return
        
        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.reject_ownership_request(request_id, file_id, "Rejected by recipient")
            )
            
            if status == 200:
                await self.app.main_window.dialog(
                    toga.InfoDialog("Rejected", f"Transfer offer rejected for: {file_name}")
                )
                await self._load_notifications_async()
            else:
                error = result.get("error", "Unknown error")
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Error", f"Failed: {error}")
                )
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed: {e}")
            )
    
    async def _on_cancel_request(self, widget):
        """Cancel an outgoing ownership request (as the CURRENT owner)."""
        request = self._get_selected_outgoing_request()
        if not request:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select Request", "Please select a request to cancel.")
            )
            return
        
        request_id = request.get("request_id")
        file_id = request.get("file_id")
        file_name = request.get("file_name", "Unknown")
        new_owner = request.get("new_owner_address", "Unknown")
        
        confirm = await self.app.main_window.dialog(
            toga.QuestionDialog(
                "Cancel Transfer",
                f"Cancel ownership transfer for: {file_name}?\n\n"
                f"Proposed recipient: {new_owner[:20]}...\n\n"
                f"The transfer offer will be withdrawn."
            )
        )
        
        if not confirm:
            return
        
        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.cancel_ownership_request(request_id, file_id)
            )
            
            if status == 200:
                await self.app.main_window.dialog(
                    toga.InfoDialog("Cancelled", f"Transfer offer cancelled for: {file_name}")
                )
                await self._load_notifications_async()
            else:
                error = result.get("error", "Unknown error")
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Error", f"Failed: {error}")
                )
        except Exception as e:
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Failed: {e}")
            )
    
    async def _load_notifications_async(self):
        """Load ownership notifications."""
        if not self.app.client:
            return
        
        if not self.app.client.is_wallet_connected():
            return
        
        try:
            loop = asyncio.get_event_loop()
            result, status = await loop.run_in_executor(
                None,
                lambda: self.app.client.get_pending_ownership_requests()
            )
            
            if self._incoming_table:
                self._incoming_table.data.clear()
            if self._outgoing_table:
                self._outgoing_table.data.clear()
            
            self._notifications_data = []
            
            if status == 200:
                incoming = result.get("incoming", [])
                outgoing = result.get("outgoing", [])
                
                # Process incoming requests (offers TO the current user)
                # "From" is the current owner offering their file
                for req in incoming:
                    req["type"] = "incoming"
                    self._notifications_data.append(req)
                    
                    if self._incoming_table:
                        # Get current owner address (who is offering)
                        from_addr = req.get("current_owner_address", req.get("owner_address", ""))
                        file_name = req.get("file_name", "Unknown")
                        price = req.get("asking_price", "0")
                        created = req.get("created_at", "")[:10]
                        status_str = req.get("status", "pending")
                        
                        self._incoming_table.data.append([
                            file_name[:20] + "..." if len(file_name) > 20 else file_name,
                            from_addr[:12] + "..." if from_addr else "Unknown",
                            str(price).replace(" BZT", ""),
                            created,
                            status_str
                        ])
                
                # Process outgoing requests (offers FROM the current user)
                # "To" is the new owner being offered the file
                for req in outgoing:
                    req["type"] = "outgoing"
                    self._notifications_data.append(req)
                    
                    if self._outgoing_table:
                        # Get new owner address (who is being offered)
                        to_addr = req.get("new_owner_address", req.get("new_owner", ""))
                        file_name = req.get("file_name", "Unknown")
                        price = req.get("asking_price", "0")
                        created = req.get("created_at", "")[:10]
                        status_str = req.get("status", "pending")
                        
                        self._outgoing_table.data.append([
                            file_name[:20] + "..." if len(file_name) > 20 else file_name,
                            to_addr[:12] + "..." if to_addr else "Unknown",
                            str(price).replace(" BZT", ""),
                            created,
                            status_str
                        ])
                
                if not incoming and self._incoming_table:
                    self._incoming_table.data.append([
                        "--", "No incoming offers", "--", "--", "--"
                    ])
                
                if not outgoing and self._outgoing_table:
                    self._outgoing_table.data.append([
                        "--", "No outgoing offers", "--", "--", "--"
                    ])
                
                self._notifications_status.text = f"Incoming offers: {len(incoming)} | Outgoing offers: {len(outgoing)}"
            else:
                self._notifications_status.text = "Failed to load notifications"
                
        except Exception as e:
            print(f"[FILES] Error loading notifications: {e}", flush=True)
            self._notifications_status.text = f"Error: {e}"
