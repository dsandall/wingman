# Wingman

> **Keep this file up to date.** After any significant change — new CLI commands, added modules,
> renamed files, changed platform logic, new env vars — update the relevant sections
> below. Stale instructions lead to wasted effort and broken assumptions. When in doubt, re-read
> the codebase and correct anything that has drifted.

## Overview

Cross-platform Python CLI tool for running multiple NetBird instances alongside the primary
installation. Each named instance gets an isolated config dir, daemon socket, and WireGuard
interface name.

## Project Structure

- `src/wingman/cli.py` — Typer app, subcommands (`up`, `down`, `status`, `list`)
- `src/wingman/instance.py` — Instance lifecycle orchestration
- `src/wingman/config.py` — Config dir resolution, instance metadata, PID files
- `src/wingman/daemon.py` — Daemon process management
- `src/wingman/netbird.py` — Shelling out to netbird binary
- `src/wingman/platform.py` — OS-specific logic (paths, sockets, interface names)
- `tests/` — Unit tests (mocked, no real netbird needed)

## Commands

```
uv sync                    # Install dependencies
uv run pytest -v           # Run tests
uv run ruff format .       # Format code
uv run ruff check --fix .  # Lint code
uv run wingman --help     # Run CLI
```

## Architecture Notes

- All platform branching is in `platform.py` — other modules are OS-agnostic
- `platform.py` now also resolves NetBird runtime details per instance (`config` path + runtime env), including Linux non-root `NB_STATE_DIR` handling
- `netbird.py` shells out to NetBird and supports runtime env injection for daemon startup; `run_up` also forwards `NB_STATE_DIR` and selects the instance's `--profile` (NetBird 0.72+) so the client doesn't fall back to the user's default profile
- `instance.py` orchestrates but delegates to `config`, `daemon`, `netbird`, and `service` modules
- Linux user systemd units include required runtime environment variables (for example `NB_STATE_DIR`) when persistence is registered
- Daemon is managed via PID files with stale-PID detection

## Environment Variables

| Variable | Purpose |
|---|---|
| `WINGMAN_MANAGEMENT_URL` | Default management URL |
| `WINGMAN_SETUP_KEY` | Default setup key |
| `WINGMAN_NETBIRD_BIN` | Path to netbird binary |
| `WINGMAN_CONFIG_DIR` | Override root config directory |
