# wingman

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Run **multiple [NetBird](https://netbird.io) networks on one machine, at the same time** — each in its own isolated config dir, daemon socket, and WireGuard interface.

Useful when a single host needs to be a peer on two separate NetBird networks at once (e.g. a *personal* net and a *work* net) so you can SSH and reach web GUIs on both — something a single NetBird daemon can't do, since it runs one profile at a time.

> Wingman is a continuation of the abandoned `twinbird` project, with the multi-instance state-isolation bug fixed, root systemd persistence, and a `peers` command.

## Install (Arch)

NetBird must be installed and on `PATH` first (it's a hard dependency, from the AUR).

```bash
git clone https://github.com/dsandall/wingman.git
cd wingman/packaging/arch
makepkg -si
```

This builds the wheel and installs `/usr/bin/wingman` (depends: `python`, `python-typer`, `netbird`).

## Usage

Creating a WireGuard interface needs `CAP_NET_ADMIN`, so run as root to be a peer on the host itself:

```bash
# Start named instances on two different networks
sudo wingman up personal --management-url https://api.netbird.io:443 --setup-key KEY1
sudo wingman up work     --management-url https://api.netbird.io:443 --setup-key KEY2

# Peers + connection status (replaces `netbird status --detail | awk`)
sudo wingman peers          # all instances
sudo wingman peers work     # one instance

# Status / list / stop
sudo wingman status
sudo wingman list
sudo wingman down work
```

Omit `--setup-key` to log in interactively via SSO/OAuth instead.

### Environment variables

```bash
export WINGMAN_MANAGEMENT_URL=https://api.netbird.io:443
export WINGMAN_SETUP_KEY=YOUR_KEY
sudo -E wingman up personal
```

| Variable | Purpose |
|---|---|
| `WINGMAN_MANAGEMENT_URL` | Default management URL |
| `WINGMAN_SETUP_KEY` | Default setup key |
| `WINGMAN_NETBIRD_BIN` | Path to netbird binary (default: `netbird` on PATH) |
| `WINGMAN_CONFIG_DIR` | Override root config directory |

## How it works

Each named instance gets:
- Its own config directory (`~/.config/wingman/<name>/` as a user, `/root/.config/wingman/<name>/` as root)
- An **isolated `NB_STATE_DIR`**, so a daemon never shares `/var/lib/netbird` with the system install (or another instance) and fight over the same WireGuard interface
- A unique daemon socket (Unix socket on Linux/macOS, TCP port on Windows)
- A unique WireGuard interface (`wt<N>` on Linux, `utun<N>` on macOS)

Wingman starts a separate `netbird service run` daemon per instance, then connects with `netbird up`. Persistence is registered as a **system** systemd unit when run as root (so instances survive reboot), or a `--user` unit otherwise.

## Development

```bash
uv sync                    # install dependencies
uv run pytest -v           # run tests (mocked, no real netbird needed)
uv run ruff check .        # lint
uv run wingman --help      # run the CLI
```

There are also Docker test harnesses under `docker/` for exercising instances in an isolated network namespace without touching the host's NetBird.

## Requirements

- [NetBird](https://netbird.io) installed and on PATH
- Python 3.10+

## License

MIT
