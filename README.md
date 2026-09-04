# wingman

[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Run **multiple [NetBird](https://netbird.io) networks on one machine, at the same time** — each in its own isolated config dir, daemon socket, and WireGuard interface.

Useful when a single host needs to be a peer on two separate NetBird networks at once (e.g. a *personal* net and a *work* net) so you can SSH and reach web GUIs on both — something a single NetBird daemon can't do, since it runs one profile at a time.

> Wingman is a continuation of the abandoned `twinbird` project, with the multi-instance state-isolation bug fixed, rootless systemd persistence, and a `peers` command.

## Install (Arch)

NetBird must be installed and on `PATH` first (it's a hard dependency, from the AUR).

```bash
paru -S wingman-git      # or yay -S wingman-git
```

`wingman-git` builds from the tip of `master` and installs `/usr/bin/wingman` (depends: `python`, `python-typer`, `netbird`). The AUR package is kept in sync with this repo automatically on every push (see `.github/workflows/aur.yml`).

To build straight from a checkout instead:

```bash
git clone https://github.com/dsandall/wingman.git
cd wingman/packaging/arch && makepkg -si
```

## Install (Ubuntu / Debian)

No native package yet, so install NetBird from its APT repo and wingman with `pipx`.
Tested on Ubuntu 26.04 (Python 3.14).

```bash
# 1. Prerequisites
sudo apt update
sudo apt install -y pipx git curl ca-certificates gnupg libcap2-bin

# 2. NetBird (hard dependency) — add its official APT repo, then install
curl -fsSL https://pkgs.netbird.io/debian/public.key \
  | sudo gpg --dearmor -o /usr/share/keyrings/netbird-archive-keyring.gpg
echo 'deb [signed-by=/usr/share/keyrings/netbird-archive-keyring.gpg] https://pkgs.netbird.io/debian stable main' \
  | sudo tee /etc/apt/sources.list.d/netbird.list
sudo apt update
sudo apt install -y netbird

# 3. wingman
pipx install git+https://github.com/dsandall/wingman.git
pipx ensurepath   # adds ~/.local/bin to PATH; open a new shell afterwards
```

### Rootless prerequisites (one time)

wingman runs rootless. Grant the `netbird` binary the capabilities it needs to
create the WireGuard interface and bind the per-instance DNS resolver:

```bash
sudo setcap cap_net_admin,cap_net_raw,cap_net_bind_service+eip "$(command -v netbird)"
```

> Unlike the Arch package's pacman hook, APT does **not** reapply file capabilities
> after a `netbird` upgrade — rerun this `setcap` whenever `apt upgrade` touches
> netbird (or wire it into an APT `DPkg::Post-Invoke` hook). `wingman up` preflights
> `CAP_NET_ADMIN` and aborts with the exact command if it has been stripped.

For NetBird name resolution to work rootless, systemd-resolved must accept
per-interface DNS from the non-root daemon. Install a polkit rule authorizing the
`sudo` group (Debian/Ubuntu's admin group; the shipped Arch rule under
`packaging/arch/` uses `wheel`):

```bash
sudo tee /etc/polkit-1/rules.d/50-wingman-netbird-dns.rules >/dev/null <<'EOF'
polkit.addRule(function(action, subject) {
    if ((action.id.indexOf("org.freedesktop.resolve1.set-") === 0 ||
         action.id == "org.freedesktop.resolve1.revert") &&
        subject.isInGroup("sudo")) {
        return polkit.Result.YES;
    }
});
EOF
```

DNS is non-fatal: without the rule the tunnel still comes up, only NetBird name
resolution breaks. `wingman up` preflights this and warns without blocking.

To keep instances running across reboot without an active login session:

```bash
sudo loginctl enable-linger "$USER"
```

## Usage

wingman runs **rootless** — daemons run as your user, no `sudo` for everyday commands. The AUR package handles the one privileged prerequisite for you (it grants `CAP_NET_ADMIN` to the `netbird` binary so it can create the WireGuard interface, and keeps it applied across netbird upgrades). For a manual install, do it once yourself:

```bash
sudo setcap cap_net_admin,cap_net_raw+eip $(command -v netbird)
```

`wingman up` preflights this and aborts with the exact command if it's missing, so you won't be left guessing.

```bash
# Start named instances on two different networks
wingman up personal --management-url https://api.netbird.io:443 --setup-key KEY1
wingman up work     --management-url https://api.netbird.io:443 --setup-key KEY2

# Peers + connection status (replaces `netbird status --detail | awk`)
wingman peers          # all instances
wingman peers work     # one instance

# Status / list / stop
wingman status
wingman list
wingman down work
```

Omit `--setup-key` to log in interactively via SSO/OAuth instead.

To keep instances running on boot without an active login session, enable linger once (the AUR package prints this reminder on install):

```bash
sudo loginctl enable-linger "$USER"
```

### Environment variables

```bash
export WINGMAN_MANAGEMENT_URL=https://api.netbird.io:443
export WINGMAN_SETUP_KEY=YOUR_KEY
wingman up personal
```

| Variable | Purpose |
|---|---|
| `WINGMAN_MANAGEMENT_URL` | Default management URL |
| `WINGMAN_SETUP_KEY` | Default setup key |
| `WINGMAN_NETBIRD_BIN` | Path to netbird binary (default: `netbird` on PATH) |
| `WINGMAN_CONFIG_DIR` | Override the config root (default: `~/.config/wingman`) |

## How it works

Each named instance gets:
- Its own config directory (`~/.config/wingman/<name>/`, user-owned)
- An **isolated `NB_STATE_DIR`**, so a daemon never shares `/var/lib/netbird` with the system install (or another instance) and fight over the same WireGuard interface
- A unique daemon socket (Unix socket on Linux/macOS, TCP port on Windows)
- A unique WireGuard interface (`wt<N>` on Linux, `utun<N>` on macOS)

On Linux the daemon lifecycle is owned by **systemd**: `up` registers a `systemctl --user` unit and starts it (so instances survive reboot once linger is enabled), and `down` stops it — `status`/`list` query systemd directly. Where no service manager is available (containers, macOS, Windows), wingman falls back to supervising a `netbird service run` daemon directly, tracked via PID files. Either way it connects with `netbird up` once the daemon is reachable.

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
