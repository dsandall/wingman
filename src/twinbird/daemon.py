from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from twinbird import netbird
from twinbird.config import read_pid, remove_pid, write_pid


def is_daemon_reachable(daemon_addr: str) -> bool:
    """Check if a daemon is listening on its address by attempting a TCP connect."""
    parsed = urlparse(daemon_addr)
    if parsed.scheme != "tcp" or not parsed.hostname or not parsed.port:
        return False
    try:
        with socket.create_connection((parsed.hostname, parsed.port), timeout=1):
            return True
    except OSError:
        return False


def is_process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return exit_code.value == STILL_ACTIVE

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_daemon(
    netbird_bin: str,
    config_path: Path,
    daemon_addr: str,
    config_root: Path,
    name: str,
    log_file: Path,
    env: dict[str, str] | None = None,
) -> int:
    proc = netbird.run_service(netbird_bin, config_path, daemon_addr, log_file, env)
    write_pid(config_root, name, proc.pid)

    for _ in range(10):
        time.sleep(0.5)
        if not is_process_alive(proc.pid):
            remove_pid(config_root, name)
            log_tail = ""
            if log_file.exists():
                lines = log_file.read_text().splitlines()
                log_tail = "\n".join(lines[-10:])
            msg = f"Daemon failed to start for instance '{name}'."
            if log_tail:
                msg += f"\n{log_tail}"
            raise RuntimeError(msg)

    return proc.pid


def stop_daemon(config_root: Path, name: str) -> None:
    pid = read_pid(config_root, name)
    if pid is None:
        return

    if not is_process_alive(pid):
        remove_pid(config_root, name)
        return

    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        PROCESS_TERMINATE = 0x0001
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            kernel32.TerminateProcess(handle, 1)
            kernel32.CloseHandle(handle)
    else:
        import signal

        os.kill(pid, signal.SIGTERM)
        for _ in range(10):
            time.sleep(0.5)
            if not is_process_alive(pid):
                break
        else:
            os.kill(pid, signal.SIGKILL)

    remove_pid(config_root, name)
