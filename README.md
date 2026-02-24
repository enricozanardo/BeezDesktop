# BeezDesktop

Native desktop client for the Beez Network, built with BeeWare (Toga + Briefcase).

## Features

- **Wallet Management**: Create, connect, and manage Beez wallets
- **File Operations**: Upload and download files to/from the Beez Network
- **Transactions**: Send BZT tokens, view transaction history
- **Blockchain Explorer**: Browse blocks, transactions, and wallets
- **Network Status**: Monitor active nodes and network health

## Architecture

BeezDesktop uses the shared client core (`shared/client_core/`) which provides:
- Wallet utilities (key generation, signing)
- File encryption/decryption
- ZeroMQ network communication
- Transaction creation and submission
- Blockchain queries

```
BeezDesktop/
├── pyproject.toml          # Briefcase configuration
├── src/
│   └── beezdesktop/
│       ├── app.py          # Main Toga application
│       ├── views/          # UI views (dashboard, wallet, files, etc.)
│       ├── components/     # Reusable UI components
│       └── resources/      # Icons and assets
└── README.md
```

## Development Setup

### Prerequisites

- Python 3.11+
- Git (with submodule support)
- System dependencies for GTK (Linux) or native GUI (macOS/Windows)

### Installation

1. **Clone with submodules** (the `shared/` folder is a git submodule pointing to BeezShared):
```bash
git clone --recurse-submodules https://github.com/enricozanardo/BeezDesktop.git
cd BeezDesktop
git checkout ez_dev
git submodule update --init --recursive
```

If you already cloned without `--recurse-submodules`, initialize the submodule:
```bash
cd BeezDesktop
git submodule update --init --recursive
```

2. **Install system dependencies** (Debian/Ubuntu):

For **Ubuntu 24.04+ / Debian 13+** (GObject Introspection 2.x):
```bash
sudo apt install libgirepository-2.0-dev libcairo2-dev libpango1.0-dev \
    libwebkit2gtk-4.1-dev gir1.2-webkit2-4.1 python3-venv python3-dev
```

For **Debian 12 / Ubuntu 22.04** (GObject Introspection 1.x):
```bash
sudo apt install libgirepository1.0-dev libcairo2-dev libpango1.0-dev \
    libwebkit2gtk-4.1-dev gir1.2-webkit2-4.1 python3-venv python3-dev
```

> **Tip**: Not sure which one? Run `apt search libgirepository` and install whichever `-dev` package is available.

3. **Create virtual environment and install Briefcase**:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install briefcase
pip install -r shared/requirements.txt
```

### Running in Development

```bash
briefcase dev
```

Briefcase automatically adds `shared/` to the Python path (configured in `pyproject.toml` under `sources`). No need to `pip install` the shared module separately.

### Building for Distribution

```bash
briefcase create
briefcase build
briefcase package
```

### Updating the Shared Module

The `shared/` folder tracks the `ez_dev` branch of BeezShared. To update:
```bash
cd shared
git pull origin ez_dev
cd ..
```

## Views

| View | Description |
|------|-------------|
| Dashboard | Quick actions and network overview |
| Wallet | Create/connect wallet, view balance |
| Files | Upload/download files |
| Transactions | Send BZT, view history |
| Blockchain | Block and transaction explorer |
| Network | Node status and connectivity |

## Configuration

BeezDesktop reads configuration from:
1. `~/.beez` configuration file
2. Environment variables
3. Default configuration from `shared/beez_config.py`

## Relationship with Other Components

- **shared/client_core/**: Core client logic (encryption, wallet, network)
- **BeezClient**: Flask API backend (same core, HTTP interface)
- **BeezFE**: React web frontend (uses BeezClient API)

BeezDesktop embeds the client core directly, providing a standalone application
without requiring a separate backend service.
