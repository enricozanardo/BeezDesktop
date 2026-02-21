"""
Settings View

Allows viewing and editing the .beez network configuration from within the app.
On first launch, loads bundled defaults. Saves to ~/.beez for persistence.
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from pathlib import Path


class SettingsView:
    """Settings view for managing .beez network configuration."""

    def __init__(self, app):
        self.app = app
        self._config = None
        self._load_current_config()

    def _load_current_config(self):
        """Load current config values for display."""
        try:
            from shared.beez_config import get_config
            self._config = get_config()
        except Exception as e:
            print(f"[SETTINGS] Could not load config: {e}", flush=True)

    def build(self) -> toga.Box:
        """Build the settings view."""
        container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        header = toga.Label(
            "Settings",
            style=Pack(padding=(0, 0, 20, 0), font_size=24, font_weight="bold")
        )
        container.add(header)

        # Config file location
        config_path = self._get_config_path()
        path_row = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 15, 0)))
        path_row.add(toga.Label(
            f"Config file: {config_path}",
            style=Pack(font_size=11, color="#666666", flex=1)
        ))
        container.add(path_row)

        # -- Network Section --
        container.add(self._section_header("Network"))

        self.network_type_input = self._add_field(
            container, "Network Type",
            self._config.network.type if self._config else "default"
        )

        dir_nodes = ", ".join(self._config.network.directory_nodes) if self._config else ""
        self.directory_nodes_input = self._add_field(
            container, "Directory Nodes (comma-separated)",
            dir_nodes,
        )

        # -- ZMQ Section --
        container.add(self._section_header("ZMQ"))

        self.zmq_tx_port_input = self._add_field(
            container, "TX Port",
            str(self._config.zmq.tx_port) if self._config else "5555"
        )
        self.zmq_consensus_port_input = self._add_field(
            container, "Consensus Port",
            str(self._config.zmq.consensus_port) if self._config else "5557"
        )
        self.zmq_timeout_input = self._add_field(
            container, "Timeout (ms)",
            str(self._config.zmq.timeout_ms) if self._config else "5000"
        )

        # -- Logging Section --
        container.add(self._section_header("Logging"))

        log_level = self._config.logging.level if self._config else "INFO"
        self.log_level_input = self._add_field(container, "Level", log_level)

        # -- Security Section --
        container.add(self._section_header("Security"))

        tls_val = str(self._config.security.enable_tls).lower() if self._config else "false"
        self.tls_input = self._add_field(container, "Enable TLS", tls_val)

        rate_limit = str(self._config.security.rate_limit) if self._config else "1000"
        self.rate_limit_input = self._add_field(container, "Rate Limit", rate_limit)

        # -- Action Buttons --
        btn_row = toga.Box(style=Pack(direction=ROW, padding=(20, 0, 0, 0)))

        save_btn = toga.Button(
            "Save & Apply",
            on_press=self._on_save,
            style=Pack(padding=5, width=140, background_color="#4caf50", color="#ffffff")
        )
        btn_row.add(save_btn)

        reset_btn = toga.Button(
            "Reset to Defaults",
            on_press=self._on_reset,
            style=Pack(padding=5, width=160)
        )
        btn_row.add(reset_btn)

        container.add(btn_row)

        # Status label
        self.status_label = toga.Label(
            "",
            style=Pack(padding=(10, 0), font_size=12, color="#666666")
        )
        container.add(self.status_label)

        return container

    # -- Helpers --

    @staticmethod
    def _section_header(title: str) -> toga.Label:
        return toga.Label(
            title,
            style=Pack(
                padding=(15, 0, 5, 0), font_size=16, font_weight="bold", color="#1565c0"
            )
        )

    @staticmethod
    def _add_field(container: toga.Box, label_text: str, value: str) -> toga.TextInput:
        row = toga.Box(style=Pack(direction=ROW, padding=(3, 0), alignment="center"))
        label = toga.Label(
            label_text,
            style=Pack(width=260, font_size=12)
        )
        row.add(label)
        text_input = toga.TextInput(
            value=value,
            style=Pack(flex=1, padding=(0, 5))
        )
        row.add(text_input)
        container.add(row)
        return text_input

    @staticmethod
    def _get_config_path() -> str:
        user_config = Path.home() / ".beez"
        if user_config.exists():
            return str(user_config)
        return str(user_config) + " (will be created on save)"

    def _build_toml(self) -> str:
        """Build TOML string from current field values."""
        nodes_raw = self.directory_nodes_input.value.strip()
        nodes = [n.strip() for n in nodes_raw.split(",") if n.strip()]
        nodes_toml = ", ".join(f'"{n}"' for n in nodes)

        tls = self.tls_input.value.strip().lower() in ("true", "1", "yes")

        return (
            f'[network]\n'
            f'type = "{self.network_type_input.value.strip()}"\n'
            f'directory_nodes = [{nodes_toml}]\n'
            f'\n'
            f'[wallet]\n'
            f'address = ""\n'
            f'mnemonic = ""\n'
            f'keystore_path = ""\n'
            f'\n'
            f'[zmq]\n'
            f'tx_port = {self.zmq_tx_port_input.value.strip()}\n'
            f'consensus_port = {self.zmq_consensus_port_input.value.strip()}\n'
            f'timeout_ms = {self.zmq_timeout_input.value.strip()}\n'
            f'reconnect_interval_ms = 1000\n'
            f'\n'
            f'[logging]\n'
            f'level = "{self.log_level_input.value.strip()}"\n'
            f'file_path = ""\n'
            f'\n'
            f'[security]\n'
            f'enable_tls = {str(tls).lower()}\n'
            f'rate_limit = {self.rate_limit_input.value.strip()}\n'
        )

    # -- Handlers --

    def _on_save(self, widget):
        """Save config to ~/.beez and reload."""
        try:
            toml_content = self._build_toml()
            config_path = Path.home() / ".beez"
            config_path.write_text(toml_content, encoding="utf-8")

            from shared.beez_config import reload_config
            self._config = reload_config(str(config_path))

            self.status_label.text = f"Saved to {config_path}. Restart app to apply network changes."
            print(f"[SETTINGS] Config saved to {config_path}", flush=True)
        except Exception as e:
            self.status_label.text = f"Error saving: {e}"
            print(f"[SETTINGS] Save error: {e}", flush=True)

    def _on_reset(self, widget):
        """Reset fields to bundled defaults."""
        try:
            from shared.beez_config import BeezConfig
            bundled = BeezConfig._find_bundled_config()
            if bundled and bundled.exists():
                default_config = BeezConfig.load(str(bundled))
            else:
                default_config = BeezConfig()

            self.network_type_input.value = default_config.network.type
            self.directory_nodes_input.value = ", ".join(default_config.network.directory_nodes)
            self.zmq_tx_port_input.value = str(default_config.zmq.tx_port)
            self.zmq_consensus_port_input.value = str(default_config.zmq.consensus_port)
            self.zmq_timeout_input.value = str(default_config.zmq.timeout_ms)
            self.log_level_input.value = default_config.logging.level
            self.tls_input.value = str(default_config.security.enable_tls).lower()
            self.rate_limit_input.value = str(default_config.security.rate_limit)

            self.status_label.text = "Reset to defaults. Click 'Save & Apply' to persist."
        except Exception as e:
            self.status_label.text = f"Error resetting: {e}"
