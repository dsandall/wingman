from __future__ import annotations

import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import typer


def _try_run(cmd: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run a command, returning None if the executable is not present.

    Service managers (systemctl, launchctl, schtasks) are absent in some
    environments — containers, minimal/non-systemd distros. In those cases
    persistence is simply skipped rather than crashing the caller.
    """
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return None


def _task_name(name: str) -> str:
    return f"twinbird-{name}"


def _build_netbird_cmd(
    netbird_bin: str,
    config_path: Path,
    daemon_addr: str,
    log_file: Path,
) -> list[str]:
    return [
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


def register_service(
    name: str,
    netbird_bin: str,
    config_path: Path,
    daemon_addr: str,
    log_file: Path,
    env: dict[str, str] | None = None,
) -> None:
    if sys.platform == "win32":
        _register_windows(name, netbird_bin, config_path, daemon_addr, log_file)
    elif sys.platform == "darwin":
        _register_macos(name, netbird_bin, config_path, daemon_addr, log_file)
    else:
        _register_linux(name, netbird_bin, config_path, daemon_addr, log_file, env)


def unregister_service(name: str) -> None:
    if sys.platform == "win32":
        _unregister_windows(name)
    elif sys.platform == "darwin":
        _unregister_macos(name)
    else:
        _unregister_linux(name)


def is_service_registered(name: str) -> bool:
    if sys.platform == "win32":
        return _is_registered_windows(name)
    elif sys.platform == "darwin":
        return _is_registered_macos(name)
    else:
        return _is_registered_linux(name)


# --- Windows: Task Scheduler ---

_TASK_XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <RunLevel>HighestAvailable</RunLevel>
      <LogonType>InteractiveToken</LogonType>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Hidden>true</Hidden>
    <Enabled>true</Enabled>
  </Settings>
  <Actions>
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _request_elevation(command_line: str) -> None:
    """Run a command line with UAC elevation via PowerShell."""
    subprocess.run(
        [
            "powershell",
            "-Command",
            f"Start-Process cmd.exe -ArgumentList '/c {command_line}' "
            "-Verb RunAs -Wait -WindowStyle Hidden",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _write_task_xml(name: str, parts: list[str]) -> Path:
    """Write a Task Scheduler XML definition to a temp file and return its path."""
    from xml.sax.saxutils import escape as xml_escape

    # Wrap in PowerShell to avoid a visible console window
    ps_args = " ".join(f"'{p}'" for p in parts)
    command = "powershell.exe"
    arguments = f'-WindowStyle Hidden -NoProfile -Command "& {ps_args}"'

    xml_content = _TASK_XML_TEMPLATE.format(
        command=xml_escape(command),
        arguments=xml_escape(arguments),
    )
    xml_file = Path(tempfile.gettempdir()) / f"twinbird-{name}.xml"
    xml_file.write_text(xml_content, encoding="utf-16")
    return xml_file


def _register_windows(
    name: str,
    netbird_bin: str,
    config_path: Path,
    daemon_addr: str,
    log_file: Path,
) -> None:
    parts = _build_netbird_cmd(netbird_bin, config_path, daemon_addr, log_file)
    task_name = _task_name(name)
    xml_file = _write_task_xml(name, parts)

    try:
        result = subprocess.run(
            ["schtasks", "/create", "/tn", task_name, "/xml", str(xml_file), "/f"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return

        typer.echo("Requesting administrator privileges to register startup task...")
        _request_elevation(f'schtasks /create /tn "{task_name}" /xml "{xml_file}" /f')

        if not _is_registered_windows(name):
            typer.echo(
                f"Warning: failed to register startup task for '{name}'.",
                err=True,
            )
    finally:
        xml_file.unlink(missing_ok=True)


def _unregister_windows(name: str) -> None:
    task_name = _task_name(name)
    result = subprocess.run(
        ["schtasks", "/delete", "/tn", task_name, "/f"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return

    if _is_registered_windows(name):
        _request_elevation(f'schtasks /delete /tn "{task_name}" /f')


def _is_registered_windows(name: str) -> bool:
    result = subprocess.run(
        ["schtasks", "/query", "/tn", _task_name(name)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


# --- Linux: systemd user unit ---


def _systemd_unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def _systemd_unit_path(name: str) -> Path:
    return _systemd_unit_dir() / f"twinbird-{name}.service"


_SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=Twinbird instance: {name}

[Service]
{environment_block}
ExecStart={exec_start}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


def _register_linux(
    name: str,
    netbird_bin: str,
    config_path: Path,
    daemon_addr: str,
    log_file: Path,
    env: dict[str, str] | None = None,
) -> None:
    unit_dir = _systemd_unit_dir()
    unit_dir.mkdir(parents=True, exist_ok=True)

    cmd_parts = _build_netbird_cmd(netbird_bin, config_path, daemon_addr, log_file)
    exec_start = " ".join(shlex.quote(part) for part in cmd_parts)
    environment_block = ""
    if env:
        lines: list[str] = []
        for key, value in sorted(env.items()):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'Environment="{key}={escaped}"')
        environment_block = "\n".join(lines)

    unit_path = _systemd_unit_path(name)
    unit_path.write_text(
        _SYSTEMD_UNIT_TEMPLATE.format(
            name=name,
            exec_start=exec_start,
            environment_block=environment_block,
        )
    )

    reload_result = _try_run(["systemctl", "--user", "daemon-reload"])
    enable_result = _try_run(
        ["systemctl", "--user", "enable", f"twinbird-{name}.service"]
    )
    if reload_result is None or enable_result is None:
        typer.echo(
            f"Note: systemctl not available; instance '{name}' is connected for "
            "this session but won't be registered to start on boot.",
            err=True,
        )
        return
    if reload_result.returncode != 0 or enable_result.returncode != 0:
        stderr = " | ".join(
            s for s in (reload_result.stderr, enable_result.stderr) if s
        )
        typer.echo(
            f"Warning: failed to register service for '{name}': {stderr}",
            err=True,
        )


def _unregister_linux(name: str) -> None:
    _try_run(["systemctl", "--user", "disable", f"twinbird-{name}.service"])
    unit_path = _systemd_unit_path(name)
    if unit_path.exists():
        unit_path.unlink()
    _try_run(["systemctl", "--user", "daemon-reload"])


def _is_registered_linux(name: str) -> bool:
    result = _try_run(["systemctl", "--user", "is-enabled", f"twinbird-{name}.service"])
    return result is not None and result.returncode == 0


# --- macOS: launchd user agent ---


def _launchd_plist_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _launchd_plist_path(name: str) -> Path:
    return _launchd_plist_dir() / f"com.twinbird.{name}.plist"


_LAUNCHD_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.twinbird.{name}</string>
    <key>ProgramArguments</key>
    <array>
{program_arguments}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_file}</string>
    <key>StandardErrorPath</key>
    <string>{log_file}</string>
</dict>
</plist>
"""


def _register_macos(
    name: str,
    netbird_bin: str,
    config_path: Path,
    daemon_addr: str,
    log_file: Path,
) -> None:
    plist_dir = _launchd_plist_dir()
    plist_dir.mkdir(parents=True, exist_ok=True)

    cmd_parts = _build_netbird_cmd(netbird_bin, config_path, daemon_addr, log_file)
    program_arguments = "\n".join(
        f"        <string>{part}</string>" for part in cmd_parts
    )

    plist_path = _launchd_plist_path(name)
    plist_path.write_text(
        _LAUNCHD_PLIST_TEMPLATE.format(
            name=name,
            program_arguments=program_arguments,
            log_file=str(log_file),
        )
    )

    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        typer.echo(
            f"Warning: failed to register service for '{name}': {result.stderr}",
            err=True,
        )


def _unregister_macos(name: str) -> None:
    plist_path = _launchd_plist_path(name)
    if plist_path.exists():
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        plist_path.unlink()


def _is_registered_macos(name: str) -> bool:
    return _launchd_plist_path(name).exists()
