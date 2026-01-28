"""
Files View

File management: upload, download, list files.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW


class FilesView:
    """File management view."""
    
    def __init__(self, app):
        self.app = app
        self.files_table = None
    
    def build(self) -> toga.Box:
        """Build the files view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Header
        header = toga.Label(
            "Files",
            style=Pack(padding=(0, 0, 20, 0), font_size=24, font_weight="bold")
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
        
        # Upload section
        upload_section = self._build_upload_section()
        container.add(upload_section)
        
        # Files list section
        files_section = self._build_files_section()
        container.add(files_section)
        
        return container
    
    def _build_upload_section(self) -> toga.Box:
        """Build the upload section."""
        section = toga.Box(
            style=Pack(direction=COLUMN, padding=10, background_color="#f5f5f5")
        )
        
        header = toga.Label(
            "Upload File",
            style=Pack(font_size=16, font_weight="bold", padding=(0, 0, 10, 0))
        )
        section.add(header)
        
        # File selection
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
        
        # Upload button
        upload_btn = toga.Button(
            "Upload to Network",
            on_press=self._on_upload_file,
            style=Pack(width=200, padding=(10, 0, 0, 0))
        )
        section.add(upload_btn)
        
        return section
    
    def _build_files_section(self) -> toga.Box:
        """Build the files list section."""
        section = toga.Box(style=Pack(direction=COLUMN, padding=10, flex=1))
        
        # Header with refresh button
        header_row = toga.Box(style=Pack(direction=ROW, padding=(20, 0, 10, 0)))
        
        header = toga.Label(
            "My Files",
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
            headings=["File Name", "Size", "Upload Date", "Status"],
            data=[],
            style=Pack(flex=1)
        )
        section.add(self.files_table)
        
        # Load files
        self._load_files()
        
        return section
    
    def _on_select_file(self, widget):
        """Handle file selection."""
        # Note: File dialog implementation depends on platform
        # This is a placeholder - in real implementation use toga.OpenFileDialog
        self.selected_file_label.text = "File selection pending..."
    
    def _on_upload_file(self, widget):
        """Handle file upload."""
        self.app.main_window.info_dialog(
            "Upload",
            "File upload functionality will be implemented.\n"
            "This requires integration with storage nodes."
        )
    
    def _on_refresh_files(self, widget):
        """Refresh the files list."""
        self._load_files()
    
    def _load_files(self):
        """Load files from blockchain."""
        if not self.app.client or not self.files_table:
            return
        
        try:
            uploads = self.app.client.get_user_uploads()
            
            # Clear and populate table
            self.files_table.data.clear()
            
            for upload in uploads:
                self.files_table.data.append([
                    upload.get("file_name", "Unknown"),
                    f"{upload.get('file_size', 0)} bytes",
                    upload.get("timestamp", "Unknown"),
                    "Confirmed"
                ])
                
        except Exception as e:
            print(f"[FILES] Error loading files: {e}", flush=True)
