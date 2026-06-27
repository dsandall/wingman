from __future__ import annotations

import getpass
import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformConfig:
    config_root: Path
    interface_prefix: str


def _is_root() -> bool:
    if hasattr(os, "getuid"):
        return os.getuid() == 0  # type: ignore[attr-defined]
    return False


def is_root() -> bool:
    """Public accessor for root/elevated status (platform branching lives here)."""
    return _is_root()


def get_platform_config() -> PlatformConfig:
    override = os.environ.get("WINGMAN_CONFIG_DIR")
    if override:
        config_root = Path(override)
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        config_root = Path(appdata if appdata else str(Path.home())) / "wingman"
    else:
        config_root = Path.home() / ".config" / "wingman"

    interface_prefix = "utun" if sys.platform == "darwin" else "wt"

    return PlatformConfig(config_root=config_root, interface_prefix=interface_prefix)


def derive_daemon_addr(name: str, config: PlatformConfig) -> str:
    if sys.platform == "win32":
        h = int(hashlib.sha256(name.encode()).hexdigest(), 16)
        port = 52160 + (h % 800)
        return f"tcp://127.0.0.1:{port}"

    if _is_root():
        return f"unix:///var/run/wingman-{name}.sock"

    sock_path = config.config_root / name / f"{name}.sock"
    return f"unix://{sock_path.as_posix()}"


def derive_interface_name(name: str, config: PlatformConfig) -> str:
    h = int(hashlib.sha256(name.encode()).hexdigest(), 16)
    index = 1 + (h % 99)
    return f"{config.interface_prefix}{index}"


def resolved_dns_authorized() -> bool | None:
    """Whether the daemon's user may configure systemd-resolved per-link DNS.

    A rootless NetBird daemon installs each instance's DNS by asking
    systemd-resolved to set the interface's DNS server/domains
    (`org.freedesktop.resolve1.set-dns-servers` et al.). polkit denies that to a
    non-root caller unless a rule grants it, and the daemon then silently fails
    to install DNS (the tunnel still comes up, but name resolution doesn't). The
    daemon runs as this process's user, so `pkcheck` against our own PID is a
    faithful proxy. Returns None when undeterminable (not Linux, no resolved, or
    `pkcheck`/resolved unavailable) so callers don't warn on a guess.
    """
    if sys.platform != "linux":
        return None
    pkcheck = shutil.which("pkcheck")
    resolvectl = shutil.which("resolvectl")
    if pkcheck is None or resolvectl is None:
        return None
    result = subprocess.run(
        [
            pkcheck,
            "--action-id",
            "org.freedesktop.resolve1.set-dns-servers",
            "--process",
            str(os.getpid()),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def derive_netbird_runtime(config_dir: Path) -> tuple[Path, dict[str, str]]:
    """Resolve netbird config path and runtime env for an instance directory."""
    if sys.platform != "linux":
        return config_dir / "config.json", {}

    # Always isolate NetBird state per instance on Linux. Without this a root
    # daemon shares the default /var/lib/netbird with the system install (and
    # any other instance), inherits its active profile, and fights over that
    # profile's interface (e.g. wt0). Non-root additionally avoids /var/lib
    # permission issues.
    env = {"NB_STATE_DIR": str(config_dir)}
    if not _is_root():
        user = getpass.getuser()
        return config_dir / user / "personal.json", env

    return config_dir / "config.json", env
