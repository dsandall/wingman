# twinbird

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![PyPI - Version](https://img.shields.io/pypi/v/twinbird)
![PyPI - Downloads](https://img.shields.io/pypi/dm/twinbird)


Manage multiple [NetBird](https://netbird.io) instances on a single machine with isolated configs, daemon sockets, and WireGuard interfaces.

## Install

```bash
uv tool install twinbird
```

or

```bash
pip install twinbird
```

## Usage

```bash
# Start a named instance
twinbird up office --management-url https://mgmt.example.com --setup-key YOUR_KEY

# Check status
twinbird status office

# List all instances
twinbird list

# Stop an instance
twinbird down office
```

### Environment Variables

Instead of passing flags every time:

```bash
export TWINBIRD_MANAGEMENT_URL=https://mgmt.example.com
export TWINBIRD_SETUP_KEY=YOUR_KEY
twinbird up office
```

| Variable | Purpose |
|---|---|
| `TWINBIRD_MANAGEMENT_URL` | Default management URL |
| `TWINBIRD_SETUP_KEY` | Default setup key |
| `TWINBIRD_NETBIRD_BIN` | Path to netbird binary (default: `netbird` on PATH) |
| `TWINBIRD_CONFIG_DIR` | Override root config directory |

## How It Works

Each named instance gets:
- Its own config directory (`~/.config/twinbird/<name>/` on Linux, `%APPDATA%/twinbird/<name>/` on Windows)
- A unique daemon socket address (Unix socket on Linux/macOS, TCP port on Windows)
- A unique WireGuard interface name (`wt<N>` on Linux, `utun<N>` on macOS)

Twinbird starts a separate `netbird service run` daemon per instance, then connects with `netbird up` — all fully isolated from the primary NetBird installation.

On Linux when running as a regular user, Twinbird automatically sets an instance-local NetBird state directory (`NB_STATE_DIR`) to avoid permission issues with `/var/lib/netbird`.

## Requirements

- [NetBird](https://netbird.io) installed and on PATH
- Python 3.10+

## License

MIT
