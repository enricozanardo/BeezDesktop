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

- Python 3.10+
- System dependencies for GTK (Linux) or native GUI (macOS/Windows)

### Installation

1. Install system dependencies (Linux):
```bash
sudo apt install libgirepository2.0-dev libcairo2-dev libpango1.0-dev libwebkit2gtk-4.1-dev
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows
```

3. Install in development mode:
```bash
# From the BeezMaster root directory
pip install -e shared/
```

4. Install Briefcase for packaging:
```bash
pip install briefcase
```

### Running in Development

```bash
cd BeezDesktop
briefcase dev
```

### Building for Distribution

```bash
# Create a runnable app
briefcase create
briefcase build

# Package as installer
briefcase package
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
