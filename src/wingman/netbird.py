from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def find_netbird_bin() -> str:
    bin_path = os.environ.get("WINGMAN_NETBIRD_BIN", "netbird")
    if bin_path != "netbird":
        if not shutil.which(bin_path):
            msg = (
                f"netbird binary not found at '{bin_path}'"
                " (set via WINGMAN_NETBIRD_BIN)."
            )
            raise FileNotFoundError(msg)
    elif shutil.which("netbird") is None:
        msg = "netbird not found on PATH. Install NetBird or set WINGMAN_NETBIRD_BIN."
        raise FileNotFoundError(msg)
    return bin_path


def run_service(
    netbird_bin: str,
    config_path: Path,
    daemon_addr: str,
    log_file: Path,
    env: Mapping[str, str] | None = None,
) -> subprocess.Popen[Any]:
    cmd = [
        netbird_bin,
        "service",
        "run",
        "--config",
        str(config_path),
        "--daemon-addr",
        daemon_addr,
        "--log-file",
        str(log_file),
    ]

    log_handle = open(log_file, "w")  # noqa: SIM115
    kwargs: dict[str, Any] = {
        "stdout": log_handle,
        "stderr": log_handle,
    }
    if env:
        kwargs["env"] = {**os.environ, **env}

    if sys.platform == "win32":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    return subprocess.Popen(cmd, **kwargs)


def run_up(
    netbird_bin: str,
    daemon_addr: str,
    management_url: str,
    setup_key: str | None = None,
    interface_name: str | None = None,
    profile: str | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        netbird_bin,
        "up",
        "--daemon-addr",
        daemon_addr,
        "--management-url",
        management_url,
    ]
    if setup_key:
        cmd += ["--setup-key", setup_key]
    if interface_name:
        cmd += ["--interface-name", interface_name]
    # NetBird 0.72+ selects a named profile; without --profile the client falls
    # back to the user's *default* active profile (in ~/.config/netbird), which
    # does not exist inside the instance's isolated NB_STATE_DIR. Pass both the
    # profile and the runtime env so the client and daemon agree on the state.
    if profile:
        cmd += ["--profile", profile]
    run_env = {**os.environ, **env} if env else None
    if setup_key:
        return subprocess.run(
            cmd, capture_output=True, text=True, check=False, env=run_env
        )
    # No setup key = interactive OAuth flow, let user see output
    return subprocess.run(cmd, text=True, check=False, env=run_env)


def run_down(
    netbird_bin: str,
    daemon_addr: str,
) -> subprocess.CompletedProcess[str]:
    cmd = [netbird_bin, "down", "--daemon-addr", daemon_addr]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def run_status(
    netbird_bin: str,
    daemon_addr: str,
    detail: bool = False,
) -> subprocess.CompletedProcess[str]:
    cmd = [netbird_bin, "status", "--daemon-addr", daemon_addr]
    if detail:
        cmd.append("--detail")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)
