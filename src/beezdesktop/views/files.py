"""
Files View

File management: upload, download, list files with full options.
Includes storage cost calculation with chunk-based pricing and live geolocation.
Split into two tabs: Upload and My Files.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
import asyncio
import os
import uuid

# Chunk size in bytes (100KB as per initial_doc.txt)
CHUNK_SIZE = 100 * 1024  # 100KB


class FilesView:
    """File management view with Upload and My Files tabs."""
    
    def __init__(self, app):
        self.app = app
        self.files_table = None
        self.selected_file_path = None
        self.selected_file_size = 0
        
        # Upload options
        self.visibility_select = None
        self.price_input = None
        self.duration_input = None
        self.node_select = None
        self.blur_select = None
        
        # Cost display
        self.cost_label = None
        
        # Geolocation
        self._user_location = None
        self._location_label = None
        
        # Tab container
        self._tab_container = None
    
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
        
        container.add(tab_buttons)
        
        # Tab content container
        self._tab_container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        container.add(self._tab_container)
        
        # Build both sections
        self._upload_section = self._build_upload_section()
        self._files_section = self._build_files_section()
        
        # Show upload tab by default
        self._tab_container.add(self._upload_section)
        
        # Fetch location in background
        asyncio.create_task(self._fetch_location())
        
        return container
    
    def _show_upload_tab(self, widget):
        """Switch to upload tab."""
        self._tab_container.clear()
        self._tab_container.add(self._upload_section)
        self._upload_tab_btn.style.background_color = "#4CAF50"
        self._files_tab_btn.style.background_color = "#dddddd"
    
    def _show_files_tab(self, widget):
        """Switch to files tab."""
        self._tab_container.clear()
        self._tab_container.add(self._files_section)
        self._upload_tab_btn.style.background_color = "#dddddd"
        self._files_tab_btn.style.background_color = "#4CAF50"
        # Refresh files when switching
        asyncio.create_task(self._load_files_async())
    
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
    
    def _build_upload_section(self) -> toga.Box:
        """Build the upload section with all options."""
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
            on_press=self._on_select_file,
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
        
        # Blur option (simplified: on/off)
        blur_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        blur_box.add(toga.Label("Preview Blur:", style=Pack(font_size=11, padding=(0, 0, 2, 0))))
        self.blur_select = toga.Selection(
            items=["none", "blur"],
            style=Pack(width=70)
        )
        blur_box.add(self.blur_select)
        row1.add(blur_box)
        
        options_box.add(row1)
        
        # Row 2: Node selection and proximity filter
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
            style=Pack(width=90)
        )
        prox_box.add(self.proximity_select)
        row2.add(prox_box)
        
        # User location
        loc_box = toga.Box(style=Pack(direction=COLUMN, padding=(0, 10, 0, 0)))
        self._location_label = toga.Label(
            "Location: Detecting...",
            style=Pack(font_size=10, color="#666666", padding=(12, 0, 0, 0))
        )
        loc_box.add(self._location_label)
        row2.add(loc_box)
        
        options_box.add(row2)
        section.add(options_box)
        
        # Cost estimate section (compact)
        cost_section = toga.Box(style=Pack(direction=COLUMN, padding=8, background_color="#fff8e1"))
        
        self.cost_label = toga.Label(
            "Select a file to calculate cost",
            style=Pack(font_size=12, color="#666666")
        )
        cost_section.add(self.cost_label)
        
        section.add(cost_section)
        
        # Storage nodes info
        storage_nodes = self._get_storage_nodes()
        storage_count = len(storage_nodes)
        
        if storage_nodes:
            prices = sorted([n.get("price_per_chunk", 1.0) for n in storage_nodes])
            price_list = ", ".join([f"{p}" for p in prices])
            nodes_info = toga.Label(
                f"Nodes: {storage_count} | Prices: {price_list} BZT/chunk",
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
            on_press=self._on_upload_file,
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
    
    def _build_files_section(self) -> toga.Box:
        """Build the files list section."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        
        # Header with refresh button
        header_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        
        header = toga.Label(
            "My Digital Assets",
            style=Pack(font_size=16, font_weight="bold", flex=1)
        )
        header_row.add(header)
        
        refresh_btn = toga.Button(
            "Refresh",
            on_press=self._on_refresh_files,
            style=Pack(width=80)
        )
        header_row.add(refresh_btn)
        
        section.add(header_row)
        
        # Files table
        self.files_table = toga.Table(
            headings=["File Name", "Size", "Visibility", "Price", "Guardian DAM", "Status"],
            data=[],
            style=Pack(flex=1),
            on_select=self._on_file_selected
        )
        section.add(self.files_table)
        
        # Action buttons
        actions_row = toga.Box(style=Pack(direction=ROW, padding=(10, 0, 0, 0)))
        
        download_btn = toga.Button(
            "Download",
            on_press=self._on_download_file,
            style=Pack(width=100, padding=(0, 5, 0, 0))
        )
        actions_row.add(download_btn)
        
        update_price_btn = toga.Button(
            "Update Price",
            on_press=self._on_update_price,
            style=Pack(width=100, padding=(0, 5, 0, 0))
        )
        actions_row.add(update_price_btn)
        
        toggle_vis_btn = toga.Button(
            "Toggle Visibility",
            on_press=self._on_toggle_visibility,
            style=Pack(width=120, padding=(0, 5, 0, 0))
        )
        actions_row.add(toggle_vis_btn)
        
        section.add(actions_row)
        
        # Load files asynchronously
        asyncio.create_task(self._load_files_async())
        
        return section
    
    def _calculate_num_chunks(self, file_size: int) -> int:
        """Calculate number of chunks for a file (100KB chunks)."""
        if file_size <= 0:
            return 0
        return (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    
    def _calculate_storage_cost(self) -> tuple:
        """Calculate storage cost based on current options."""
        if not self.selected_file_size:
            return 0, "No file selected", 0
        
        num_chunks = self._calculate_num_chunks(self.selected_file_size)
        
        duration_str = self.duration_input.value if self.duration_input else "5 years"
        duration = int(duration_str.split()[0])
        
        node_mode = self.node_select.value if self.node_select else "reputation"
        
        storage_nodes = self._get_storage_nodes()
        
        if not storage_nodes:
            price_per_chunk = 1.0
        else:
            prices = [n.get("price_per_chunk", 1.0) for n in storage_nodes]
            
            if node_mode == "price":
                price_per_chunk = min(prices)
            elif node_mode == "reputation":
                sorted_nodes = sorted(storage_nodes, key=lambda n: n.get("reputation", 0), reverse=True)
                price_per_chunk = sorted_nodes[0].get("price_per_chunk", 1.0) if sorted_nodes else 1.0
            else:
                price_per_chunk = sum(prices) / len(prices)
        
        cost = num_chunks * price_per_chunk * duration
        
        breakdown = f"{num_chunks} chunks × {price_per_chunk:.1f} BZT × {duration} yr = {cost:.2f} BZT"
        
        return cost, breakdown, price_per_chunk
    
    def _update_cost_estimate(self, widget=None):
        """Update the cost estimate display."""
        if not self.cost_label:
            return
        
        cost, breakdown, _ = self._calculate_storage_cost()
        
        if cost > 0:
            self.cost_label.text = f"Cost: {cost:.2f} BZT ({breakdown})"
        else:
            self.cost_label.text = "Select a file to calculate cost"
    
    def _on_node_selection_change(self, widget):
        """Handle node selection mode change."""
        self._update_cost_estimate()
    
    async def _on_select_file(self, widget):
        """Handle file selection."""
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
        if not self.selected_file_path:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file first.")
            )
            return
        
        storage_nodes = self._get_storage_nodes()
        if not self.app.client or not storage_nodes:
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
        
        proximity_str = self.proximity_select.value if self.proximity_select else "Any"
        max_distance = None
        if proximity_str != "Any":
            max_distance = int(proximity_str.split()[0])
        
        # Get blur value (simplified: "none" or "blur")
        blur_value = self.blur_select.value if self.blur_select else "none"
        
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
                f"Preview Blur: {blur_value}\n\n"
                "Proceed with upload?"
            )
        )
        
        if not confirm:
            return
        
        self.upload_status.text = "Uploading..."
        
        try:
            loop = asyncio.get_event_loop()
            
            file_id = str(uuid.uuid4())
            
            wallet = self.app.client.get_current_wallet()
            if not wallet:
                raise Exception("No wallet connected")
            
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
                    blur_level=blur_value
                )
            )
            
            if status in (200, 201):
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
                self.upload_status.text = f"✗ Error: {error}"
                await self.app.main_window.dialog(
                    toga.ErrorDialog("Upload Failed", f"Error: {error}")
                )
            
        except Exception as e:
            self.upload_status.text = f"✗ Error: {e}"
            await self.app.main_window.dialog(
                toga.ErrorDialog("Error", f"Upload failed: {e}")
            )
    
    def _on_refresh_files(self, widget):
        """Refresh the files list."""
        asyncio.create_task(self._load_files_async())
    
    def _on_file_selected(self, widget):
        """Handle file selection in table."""
        pass
    
    async def _on_download_file(self, widget):
        """Handle file download."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to download.")
            )
            return
        
        await self.app.main_window.dialog(
            toga.InfoDialog(
                "Download",
                "Download feature coming soon.\n\n"
                "Will retrieve chunks from storage nodes and reassemble."
            )
        )
    
    async def _on_update_price(self, widget):
        """Handle price update."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to update.")
            )
            return
        
        await self.app.main_window.dialog(
            toga.InfoDialog(
                "Update Price",
                "Price update feature coming soon."
            )
        )
    
    async def _on_toggle_visibility(self, widget):
        """Handle visibility toggle."""
        if not self.files_table or not self.files_table.selection:
            await self.app.main_window.dialog(
                toga.InfoDialog("Select File", "Please select a file to update.")
            )
            return
        
        await self.app.main_window.dialog(
            toga.InfoDialog(
                "Toggle Visibility",
                "Visibility toggle feature coming soon."
            )
        )
    
    async def _load_files_async(self):
        """Load files from blockchain asynchronously."""
        if not self.app.client or not self.files_table:
            return
        
        if not self.app.client.is_wallet_connected():
            return
        
        try:
            loop = asyncio.get_event_loop()
            uploads = await loop.run_in_executor(
                None, self.app.client.get_user_uploads
            )
            
            self.files_table.data.clear()
            
            if not uploads:
                self.files_table.data.append([
                    "--", "No files uploaded yet", "--", "--", "--", "--"
                ])
                return
            
            for upload in uploads:
                if upload is None:
                    continue
                    
                file_name = upload.get("file_name", "Unknown")
                file_size = upload.get("file_size", 0)
                visibility = upload.get("visibility", "private")
                price = upload.get("price", upload.get("new_price", "0"))
                guardian_dam = upload.get("guardian_dam_id", "")
                status = upload.get("status", "confirmed")
                
                # Truncate guardian DAM ID for display
                dam_display = guardian_dam[:12] + "..." if guardian_dam and len(guardian_dam) > 12 else (guardian_dam or "None")
                
                # Status display with icon
                status_display = "✓ Confirmed" if status == "confirmed" else "⏳ Pending"
                
                self.files_table.data.append([
                    file_name[:25] + "..." if len(file_name) > 25 else file_name,
                    f"{file_size:,}" if file_size else "--",
                    visibility,
                    f"{price}" if price and price != "0" else "Free",
                    dam_display,
                    status_display
                ])
                
        except Exception as e:
            print(f"[FILES] Error loading files: {e}", flush=True)
