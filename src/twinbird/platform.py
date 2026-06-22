from __future__ import annotations

import getpass
import hashlib
import os
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


def get_platform_config() -> PlatformConfig:
    override = os.environ.get("TWINBIRD_CONFIG_DIR")
    if override:
        config_root = Path(override)
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        config_root = Path(appdata if appdata else str(Path.home())) / "twinbird"
    else:
        config_root = Path.home() / ".config" / "twinbird"

    interface_prefix = "utun" if sys.platform == "darwin" else "wt"

    return PlatformConfig(config_root=config_root, interface_prefix=interface_prefix)


def derive_daemon_addr(name: str, config: PlatformConfig) -> str:
    if sys.platform == "win32":
        h = int(hashlib.sha256(name.encode()).hexdigest(), 16)
        port = 52160 + (h % 800)
        return f"tcp://127.0.0.1:{port}"

    if _is_root():
        return f"unix:///var/run/twinbird-{name}.sock"

    sock_path = config.config_root / name / f"{name}.sock"
    return f"unix://{sock_path.as_posix()}"


def derive_interface_name(name: str, config: PlatformConfig) -> str:
    h = int(hashlib.sha256(name.encode()).hexdigest(), 16)
    index = 1 + (h % 99)
    return f"{config.interface_prefix}{index}"


def derive_netbird_runtime(config_dir: Path) -> tuple[Path, dict[str, str]]:
    """Resolve netbird config path and runtime env for an instance directory."""
    if sys.platform == "linux" and not _is_root():
        user = getpass.getuser()
        return config_dir / user / "personal.json", {"NB_STATE_DIR": str(config_dir)}

    return config_dir / "config.json", {}
