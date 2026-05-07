"""
Settings View

View and edit the .beez network configuration from within the app.
On first launch, loads bundled defaults. Saves to ~/.beez for persistence.
"""

import logging
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from pathlib import Path

from beezdesktop import __version__
from beezdesktop.logging_config import get_log_path
from beezdesktop.theme import (
    Colors, Font, Spacing,
    page_header, card, spacer,
    primary_button, secondary_button, danger_button,
)
from beezdesktop.views.lifecycle import ViewLifecycle

logger = logging.getLogger("beezdesktop.settings")


class SettingsView(ViewLifecycle):
    """Settings view for managing .beez network configuration."""

    def __init__(self, app):
        ViewLifecycle.__init__(self, app)
        self._config = None
        self._load_current_config()

    def _load_current_config(self):
        try:
            from shared.beez_config import get_config
            self._config = get_config()
        except Exception as e:
            logger.info(f"[SETTINGS] Could not load config: {e}")

    def build(self) -> toga.Box:
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        container.add(page_header("Settings", f"Beez Desktop v{__version__}"))

        # Config path
        config_path = self._get_config_path()
        container.add(toga.Label(
            f"Config: {config_path}",
            style=Pack(font_size=Font.SIZE_CAPTION, color=Colors.TEXT_MUTED, padding=(0, 0, Spacing.MD, 0)),
        ))

        # Network section
        net_card = card(title="Network", bg=Colors.BG_CARD)
        self.network_type_input = self._field(net_card, "Network Type",
            self._config.network.type if self._config else "default")
        dir_nodes = ", ".join(self._config.network.directory_nodes) if self._config else ""
        self.directory_nodes_input = self._field(net_card, "Directory Nodes (comma-separated)", dir_nodes)
        container.add(net_card)
        container.add(spacer(Spacing.SM))

        # ZMQ section
        zmq_card = card(title="ZMQ", bg=Colors.BG_CARD)
        self.zmq_tx_port_input = self._field(zmq_card, "TX Port",
            str(self._config.zmq.tx_port) if self._config else "5555")
        self.zmq_consensus_port_input = self._field(zmq_card, "Consensus Port",
            str(self._config.zmq.consensus_port) if self._config else "5557")
        self.zmq_timeout_input = self._field(zmq_card, "Timeout (ms)",
            str(self._config.zmq.timeout_ms) if self._config else "5000")
        container.add(zmq_card)
        container.add(spacer(Spacing.SM))

        # Logging section
        log_card = card(title="Logging", bg=Colors.BG_CARD)
        self.log_level_input = self._field(log_card, "Level",
            self._config.logging.level if self._config else "INFO")
        container.add(log_card)
        container.add(spacer(Spacing.SM))

        # Security section
        sec_card = card(title="Security", bg=Colors.BG_CARD)
        tls_val = str(self._config.security.enable_tls).lower() if self._config else "false"
        self.tls_input = self._field(sec_card, "Enable TLS", tls_val)
        self.rate_limit_input = self._field(sec_card, "Rate Limit",
            str(self._config.security.rate_limit) if self._config else "1000")
        container.add(sec_card)
        container.add(spacer(Spacing.SM))

        # Logs section
        log_card = card(title="Application Logs", bg=Colors.BG_CARD)
        log_path = str(get_log_path())
        log_path_row = toga.Box(style=Pack(direction=ROW, padding=Spacing.XS, alignment="center"))
        log_path_row.add(toga.Label(
            "Log file",
            style=Pack(width=260, font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY),
        ))
        log_path_row.add(toga.Label(
            log_path,
            style=Pack(flex=1, font_size=Font.SIZE_CAPTION, color=Colors.TEXT_MUTED),
        ))
        log_card.add(log_path_row)

        open_log_btn_row = toga.Box(style=Pack(direction=ROW, padding=(Spacing.SM, Spacing.XS)))
        open_log_btn_row.add(secondary_button("Open Log File", self._on_open_log))
        open_log_btn_row.add(toga.Box(style=Pack(width=Spacing.SM)))
        open_log_btn_row.add(secondary_button("Open Log Folder", self._on_open_log_folder))
        log_card.add(open_log_btn_row)
        container.add(log_card)
        container.add(spacer(Spacing.MD))

        # Action buttons
        btn_row = toga.Box(style=Pack(direction=ROW))
        btn_row.add(primary_button("Save & Apply", self._on_save))
        btn_row.add(toga.Box(style=Pack(width=Spacing.SM)))
        btn_row.add(secondary_button("Reset to Defaults", self._on_reset))
        container.add(btn_row)

        # Status
        self.status_label = toga.Label(
            "",
            style=Pack(padding=(Spacing.MD, 0), font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY),
        )
        container.add(self.status_label)

        return container

    # ------------------------------------------------------------------ #

    @staticmethod
    def _field(parent: toga.Box, label_text: str, value: str) -> toga.TextInput:
        row = toga.Box(style=Pack(direction=ROW, padding=Spacing.XS, alignment="center"))
        row.add(toga.Label(
            label_text,
            style=Pack(width=260, font_size=Font.SIZE_BODY, color=Colors.TEXT_SECONDARY),
        ))
        inp = toga.TextInput(value=value, style=Pack(flex=1))
        row.add(inp)
        parent.add(row)
        return inp

    @staticmethod
    def _get_config_path() -> str:
        p = Path.home() / ".beez"
        return str(p) if p.exists() else f"{p} (will be created on save)"

    def _build_toml(self) -> str:
        nodes_raw = self.directory_nodes_input.value.strip()
        nodes = [n.strip() for n in nodes_raw.split(",") if n.strip()]
        nodes_toml = ", ".join(f'"{n}"' for n in nodes)
        tls = self.tls_input.value.strip().lower() in ("true", "1", "yes")

        return (
            f'[network]\n'
            f'type = "{self.network_type_input.value.strip()}"\n'
            f'directory_nodes = [{nodes_toml}]\n\n'
            f'[wallet]\naddress = ""\nmnemonic = ""\nkeystore_path = ""\n\n'
            f'[zmq]\n'
            f'tx_port = {self.zmq_tx_port_input.value.strip()}\n'
            f'consensus_port = {self.zmq_consensus_port_input.value.strip()}\n'
            f'timeout_ms = {self.zmq_timeout_input.value.strip()}\n'
            f'reconnect_interval_ms = 1000\n\n'
            f'[logging]\nlevel = "{self.log_level_input.value.strip()}"\nfile_path = ""\n\n'
            f'[security]\n'
            f'enable_tls = {str(tls).lower()}\n'
            f'rate_limit = {self.rate_limit_input.value.strip()}\n'
        )

    # ------------------------------------------------------------------ #
    # HANDLERS
    # ------------------------------------------------------------------ #

    def _on_save(self, widget):
        try:
            toml = self._build_toml()
            path = Path.home() / ".beez"
            path.write_text(toml, encoding="utf-8")
            from shared.beez_config import reload_config
            self._config = reload_config(str(path))
            self.status_label.text = f"Saved to {path}. Restart app for network changes."
        except Exception as e:
            self.status_label.text = f"Error: {e}"

    def _on_open_log(self, widget):
        """Open the log file with the system default text editor."""
        import subprocess, sys
        log_path = get_log_path()
        if not log_path.exists():
            self.status_label.text = "Log file does not exist yet."
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(log_path)])
            elif sys.platform == "win32":
                subprocess.Popen(["notepad", str(log_path)])
            else:
                subprocess.Popen(["xdg-open", str(log_path)])
        except Exception as e:
            self.status_label.text = f"Could not open log: {e}"

    def _on_open_log_folder(self, widget):
        """Open the log folder in the system file manager."""
        import subprocess, sys
        log_dir = get_log_path().parent
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(log_dir)])
            elif sys.platform == "win32":
                subprocess.Popen(["explorer", str(log_dir)])
            else:
                subprocess.Popen(["xdg-open", str(log_dir)])
        except Exception as e:
            self.status_label.text = f"Could not open folder: {e}"

    def _on_reset(self, widget):
        try:
            from shared.beez_config import BeezConfig
            bundled = BeezConfig._find_bundled_config()
            d = BeezConfig.load(str(bundled)) if bundled and bundled.exists() else BeezConfig()
            self.network_type_input.value = d.network.type
            self.directory_nodes_input.value = ", ".join(d.network.directory_nodes)
            self.zmq_tx_port_input.value = str(d.zmq.tx_port)
            self.zmq_consensus_port_input.value = str(d.zmq.consensus_port)
            self.zmq_timeout_input.value = str(d.zmq.timeout_ms)
            self.log_level_input.value = d.logging.level
            self.tls_input.value = str(d.security.enable_tls).lower()
            self.rate_limit_input.value = str(d.security.rate_limit)
            self.status_label.text = "Reset to defaults. Click 'Save & Apply' to persist."
        except Exception as e:
            self.status_label.text = f"Error: {e}"
