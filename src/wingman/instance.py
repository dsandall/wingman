from __future__ import annotations

import re
import shutil
import time
from datetime import datetime, timezone

import typer

from wingman.config import (
    InstanceMetadata,
    ensure_instance_dir,
    list_instances,
    read_metadata,
    read_pid,
    remove_pid,
    seed_netbird_config,
    write_metadata,
)
from wingman.daemon import (
    is_daemon_reachable,
    is_process_alive,
    start_daemon,
    stop_daemon,
)
from wingman.netbird import (
    find_netbird_bin,
    has_net_admin_capability,
    run_down,
    run_status,
    run_up,
)
from wingman.platform import (
    PlatformConfig,
    derive_daemon_addr,
    derive_interface_name,
    derive_netbird_runtime,
    get_platform_config,
    is_root,
)
from wingman.service import (
    is_service_active,
    is_service_registered,
    register_service,
    service_main_pid,
    start_service,
    stop_service,
    unregister_service,
)


def _require_kernel_iface_capability(netbird_bin: str) -> None:
    """Block a rootless `up` early when netbird can't create the WG interface.

    A non-root daemon needs CAP_NET_ADMIN on the netbird binary; without it the
    daemon starts but `netbird up` fails deep inside with "link add: operation
    not permitted", leaving an orphaned daemon. Fail fast with the one-time fix
    instead. Root always has the capability, and an undeterminable result (no
    `getcap`) is not treated as missing.
    """
    if is_root() or has_net_admin_capability(netbird_bin) is not False:
        return
    target = shutil.which(netbird_bin) or netbird_bin
    typer.echo(
        "netbird lacks CAP_NET_ADMIN, so a rootless daemon can't create the "
        "WireGuard interface. Grant it once (persists until netbird is "
        f"upgraded):\n  sudo setcap 'cap_net_admin,cap_net_raw+eip' {target}\n"
        "then re-run. (The packaged install configures this for you.)",
        err=True,
    )
    raise typer.Exit(1)


def _instance_running(name: str, platform: PlatformConfig) -> bool:
    """Whether the instance's daemon is up — service-managed or supervised."""
    if is_service_active(name):
        return True
    pid = read_pid(platform.config_root, name)
    return pid is not None and is_process_alive(pid)


def _wait_daemon_ready(netbird_bin: str, daemon_addr: str, attempts: int = 20) -> bool:
    """Poll until the daemon answers on its socket — systemd start is async."""
    for _ in range(attempts):
        time.sleep(0.25)
        if run_status(netbird_bin, daemon_addr).returncode == 0:
            return True
    return False


def _start_instance_daemon(
    name: str,
    netbird_bin: str,
    config_path,
    daemon_addr: str,
    log_file,
    runtime_env: dict[str, str],
    platform: PlatformConfig,
) -> tuple[int | None, bool]:
    """Bring the daemon up, preferring the service manager (systemd).

    Returns (pid, managed). When managed, systemd owns and supervises the
    process (no PID file). Otherwise — no service manager available (containers,
    macOS, Windows) — we supervise a daemon directly, as before.
    """
    register_service(
        name=name,
        netbird_bin=netbird_bin,
        config_path=config_path,
        daemon_addr=daemon_addr,
        log_file=log_file,
        env=runtime_env,
    )
    started = start_service(name)
    if started is None:
        pid = start_daemon(
            netbird_bin=netbird_bin,
            config_path=config_path,
            daemon_addr=daemon_addr,
            config_root=platform.config_root,
            name=name,
            log_file=log_file,
            env=runtime_env,
        )
        return pid, False

    if not started or not _wait_daemon_ready(netbird_bin, daemon_addr):
        typer.echo(
            f"Service for '{name}' failed to start. Check the daemon log "
            f"({log_file}) or the unit status.",
            err=True,
        )
        raise typer.Exit(1)
    # systemd supervises the process now; drop any stale supervised-PID file.
    remove_pid(platform.config_root, name)
    return service_main_pid(name), True


def up(
    name: str,
    management_url: str,
    setup_key: str | None = None,
    interface_name: str | None = None,
    daemon_addr: str | None = None,
) -> None:
    netbird_bin = find_netbird_bin()
    _require_kernel_iface_capability(netbird_bin)
    platform = get_platform_config()
    config_dir = ensure_instance_dir(platform.config_root, name)
    config_path, runtime_env = derive_netbird_runtime(config_dir)
    log_file = config_dir / "daemon.log"

    resolved_addr = daemon_addr or derive_daemon_addr(name, platform)
    resolved_iface = interface_name or derive_interface_name(name, platform)

    metadata = read_metadata(platform.config_root, name)
    if _instance_running(name, platform):
        if metadata is not None:
            if not is_service_registered(name):
                register_service(
                    name=name,
                    netbird_bin=netbird_bin,
                    config_path=config_path,
                    daemon_addr=metadata.daemon_addr,
                    log_file=log_file,
                    env=runtime_env,
                )
                metadata.service_registered = True
                write_metadata(platform.config_root, metadata)
            typer.echo(f"Instance '{name}' is already running.")
            return
        # Running without metadata — a leftover from a failed start. Tear it
        # down (service and/or supervised daemon) and start cleanly.
        typer.echo(f"Cleaning up orphaned instance '{name}'...")
        stop_service(name)
        stop_daemon(platform.config_root, name)

    pid = read_pid(platform.config_root, name)
    if pid:
        remove_pid(platform.config_root, name)

    seed_netbird_config(config_path, resolved_iface)

    typer.echo(f"Starting daemon for instance '{name}'...")
    daemon_pid, managed = _start_instance_daemon(
        name=name,
        netbird_bin=netbird_bin,
        config_path=config_path,
        daemon_addr=resolved_addr,
        log_file=log_file,
        runtime_env=runtime_env,
        platform=platform,
    )

    # NetBird namespaces profiles in a per-user subdir (e.g. <state>/<user>/
    # personal.json); the profile name is that file's stem. The flat root-style
    # config.json (config_path.parent == config_dir) predates profiles and needs
    # no --profile selector.
    profile = config_path.stem if config_path.parent != config_dir else None

    typer.echo(f"Connecting to {management_url}...")
    result = run_up(
        netbird_bin,
        resolved_addr,
        management_url,
        setup_key,
        resolved_iface,
        profile=profile,
        env=runtime_env,
    )
    if result.returncode != 0:
        typer.echo(f"Failed to connect: {result.stderr}", err=True)
        raise typer.Exit(1)

    metadata = InstanceMetadata(
        name=name,
        management_url=management_url,
        daemon_addr=resolved_addr,
        interface_name=resolved_iface,
        pid=daemon_pid or 0,
        created_at=datetime.now(timezone.utc).isoformat(),
        service_registered=True,
    )
    write_metadata(platform.config_root, metadata)
    where = "systemd" if managed else f"PID {daemon_pid}"
    typer.echo(f"Instance '{name}' is up ({where}, interface {resolved_iface}).")


def down(name: str) -> None:
    platform = get_platform_config()
    metadata = read_metadata(platform.config_root, name)

    if metadata is None:
        typer.echo(f"Instance '{name}' not found.", err=True)
        raise typer.Exit(1)

    netbird_bin = find_netbird_bin()
    active = is_service_active(name)
    pid = read_pid(platform.config_root, name)
    supervised = pid is not None and is_process_alive(pid)

    if not active and not supervised:
        if pid is not None:
            remove_pid(platform.config_root, name)
        run_down(netbird_bin, metadata.daemon_addr)  # best-effort disconnect
        unregister_service(name)
        typer.echo(f"Instance '{name}' is not running (cleaned up).")
        return

    typer.echo(f"Disconnecting instance '{name}'...")
    result = run_down(netbird_bin, metadata.daemon_addr)
    if result.returncode != 0:
        typer.echo(f"Warning: disconnect failed: {result.stderr}", err=True)

    if active:
        typer.echo("Stopping service...")
        stop_service(name)
    if supervised:
        typer.echo(f"Stopping daemon (PID {pid})...")
        stop_daemon(platform.config_root, name)

    unregister_service(name)
    typer.echo(f"Instance '{name}' is down.")


def status(name: str | None = None) -> None:
    platform = get_platform_config()

    if name:
        _show_instance_status(name, platform)
    else:
        instances = list_instances(platform.config_root)
        if not instances:
            typer.echo("No instances found.")
            return
        for inst_name in instances:
            _show_instance_status(inst_name, platform)


def _show_instance_status(name: str, platform: PlatformConfig) -> None:
    metadata = read_metadata(platform.config_root, name)
    if metadata is None:
        typer.echo(f"{name}: not found")
        return

    active = is_service_active(name)
    pid = None if active else read_pid(platform.config_root, name)
    alive = active or (pid is not None and is_process_alive(pid))
    reachable = not alive and is_daemon_reachable(metadata.daemon_addr)

    if alive or reachable:
        netbird_bin = find_netbird_bin()
        result = run_status(netbird_bin, metadata.daemon_addr)
        if active:
            label = "systemd"
        elif alive:
            label = f"PID {pid}"
        else:
            label = "service"
        typer.echo(f"--- {name} ({label}) ---")
        typer.echo(result.stdout or result.stderr)
    else:
        typer.echo(f"--- {name} (stopped) ---")


# A peer block in `netbird status --detail` looks like:
#   lynx.netbird.cloud:
#     NetBird IP: 100.64.135.69
#     Status: Connected
# Header = indented FQDN ending in ':'; status = indented "Status: <value>".
_PEER_HEADER_RE = re.compile(r"^\s+(\S+\.\S+):$")
_PEER_STATUS_RE = re.compile(r"^\s+Status:\s*(\S+)")


def _parse_peer_lines(detail_output: str) -> list[tuple[str, str]]:
    """Extract (short_name, status) pairs from `netbird status --detail` output."""
    peers: list[tuple[str, str]] = []
    current: str | None = None
    for line in detail_output.splitlines():
        header = _PEER_HEADER_RE.match(line)
        if header:
            current = header.group(1).split(".", 1)[0]
            continue
        status = _PEER_STATUS_RE.match(line)
        if status and current is not None:
            peers.append((current, status.group(1)))
            current = None
    return peers


# Display ordering within a network: connected first, then connecting, then the
# rest (NetBird reports offline/lazy peers as "Idle", others as "Disconnected").
_STATUS_RANK = {"connected": 0, "connecting": 1}
_STATUS_COLOR = {
    "connected": typer.colors.GREEN,
    "connecting": typer.colors.YELLOW,
}


def _peer_sort_key(peer: tuple[str, str]) -> tuple[int, str]:
    name, status = peer
    return (_STATUS_RANK.get(status.lower(), 2), name.lower())


def _styled_status(status: str) -> str:
    color = _STATUS_COLOR.get(status.lower())
    return typer.style(status, fg=color) if color else status


def _show_instance_peers(name: str, platform: PlatformConfig) -> None:
    metadata = read_metadata(platform.config_root, name)
    if metadata is None:
        typer.echo(f"{name}: not found")
        return

    netbird_bin = find_netbird_bin()
    result = run_status(netbird_bin, metadata.daemon_addr, detail=True)
    if result.returncode != 0:
        typer.echo(f"--- {name} (unreachable) ---")
        return

    typer.echo(f"--- {name} ---")
    peers = _parse_peer_lines(result.stdout)
    if not peers:
        typer.echo("(no peers)")
        return
    for peer_name, status in sorted(peers, key=_peer_sort_key):
        typer.echo(f"{peer_name} — {_styled_status(status)}")


def peers(name: str | None = None) -> None:
    platform = get_platform_config()

    if name:
        _show_instance_peers(name, platform)
        return

    instances = list_instances(platform.config_root)
    if not instances:
        typer.echo("No instances found.")
        return
    for inst_name in instances:
        _show_instance_peers(inst_name, platform)


def list_all() -> None:
    platform = get_platform_config()
    instances = list_instances(platform.config_root)

    if not instances:
        typer.echo("No instances found.")
        return

    for name in instances:
        alive = is_service_active(name)
        if not alive:
            pid = read_pid(platform.config_root, name)
            alive = pid is not None and is_process_alive(pid)
        if not alive:
            metadata = read_metadata(platform.config_root, name)
            if metadata and is_daemon_reachable(metadata.daemon_addr):
                alive = True
        state = "running" if alive else "stopped"
        if alive and is_service_registered(name):
            state = "running (persistent)"
        typer.echo(f"{name}: {state}")
