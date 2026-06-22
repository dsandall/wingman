from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class InstanceMetadata:
    name: str
    management_url: str
    daemon_addr: str
    interface_name: str
    pid: int
    created_at: str
    service_registered: bool = False


def instance_dir(config_root: Path, name: str) -> Path:
    return config_root / name


def ensure_instance_dir(config_root: Path, name: str) -> Path:
    path = instance_dir(config_root, name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def seed_netbird_config(config_path: Path, interface_name: str) -> None:
    """Ensure the NetBird config file has the correct WgIface before daemon start."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, ValueError):
            data = {}
    else:
        data = {}
    if data.get("WgIface") != interface_name:
        data["WgIface"] = interface_name
        config_path.write_text(json.dumps(data, indent=2))


def write_metadata(config_root: Path, metadata: InstanceMetadata) -> None:
    path = instance_dir(config_root, metadata.name) / "instance.json"
    path.write_text(json.dumps(asdict(metadata), indent=2))


def read_metadata(config_root: Path, name: str) -> InstanceMetadata | None:
    path = instance_dir(config_root, name) / "instance.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    data.setdefault("service_registered", False)
    return InstanceMetadata(**data)


def list_instances(config_root: Path) -> list[str]:
    if not config_root.exists():
        return []
    return [
        d.name
        for d in sorted(config_root.iterdir())
        if d.is_dir() and (d / "instance.json").exists()
    ]


def pid_file_path(config_root: Path, name: str) -> Path:
    return instance_dir(config_root, name) / "daemon.pid"


def write_pid(config_root: Path, name: str, pid: int) -> None:
    pid_file_path(config_root, name).write_text(str(pid))


def read_pid(config_root: Path, name: str) -> int | None:
    path = pid_file_path(config_root, name)
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def remove_pid(config_root: Path, name: str) -> None:
    path = pid_file_path(config_root, name)
    if path.exists():
        path.unlink()
