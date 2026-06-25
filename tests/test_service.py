from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


class TestWindowsRegister:
    def test_creates_scheduled_task_directly(self, tmp_path: Path) -> None:
        from wingman.service import register_service

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("wingman.service.sys.platform", "win32"),
            patch("wingman.service.subprocess.run", mock_run),
            patch("wingman.service.tempfile.gettempdir", return_value=str(tmp_path)),
        ):
            register_service(
                name="office",
                netbird_bin="C:/Program Files/netbird/netbird.exe",
                config_path=Path(
                    "C:/Users/user/AppData/Roaming/wingman/office/config.json"
                ),
                daemon_addr="tcp://127.0.0.1:52200",
                log_file=Path(
                    "C:/Users/user/AppData/Roaming/wingman/office/daemon.log"
                ),
            )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "schtasks"
        assert "/create" in cmd
        assert "/xml" in cmd
        assert "wingman-office" in cmd

    def test_elevates_when_access_denied(self, tmp_path: Path) -> None:
        from wingman.service import register_service

        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=1, stderr="access denied"),  # direct create
                MagicMock(returncode=0),  # powershell elevation
                MagicMock(returncode=0),  # _is_registered query
            ]
        )
        with (
            patch("wingman.service.sys.platform", "win32"),
            patch("wingman.service.subprocess.run", mock_run),
            patch("wingman.service.tempfile.gettempdir", return_value=str(tmp_path)),
        ):
            register_service(
                name="office",
                netbird_bin="netbird",
                config_path=Path(
                    "C:/Users/user/AppData/Roaming/wingman/office/config.json"
                ),
                daemon_addr="tcp://127.0.0.1:52200",
                log_file=Path(
                    "C:/Users/user/AppData/Roaming/wingman/office/daemon.log"
                ),
            )

        assert mock_run.call_count == 3
        # Second call should be powershell elevation
        ps_cmd = mock_run.call_args_list[1][0][0]
        assert ps_cmd[0] == "powershell"
        assert "RunAs" in ps_cmd[2]

    def test_register_warns_on_failure(self, tmp_path: Path, capsys) -> None:
        from wingman.service import register_service

        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=1, stderr="access denied"),  # direct create
                MagicMock(returncode=0),  # powershell elevation
                MagicMock(returncode=1),  # _is_registered query -> still not there
            ]
        )
        with (
            patch("wingman.service.sys.platform", "win32"),
            patch("wingman.service.subprocess.run", mock_run),
            patch("wingman.service.tempfile.gettempdir", return_value=str(tmp_path)),
        ):
            register_service(
                name="office",
                netbird_bin="netbird",
                config_path=Path("/tmp/wingman/office/config.json"),
                daemon_addr="tcp://127.0.0.1:52200",
                log_file=Path("/tmp/wingman/office/daemon.log"),
            )
        captured = capsys.readouterr()
        assert "Warning" in captured.err

    def test_xml_contains_highest_run_level(self, tmp_path: Path) -> None:
        from wingman.service import _build_netbird_cmd, _write_task_xml

        parts = _build_netbird_cmd(
            "netbird",
            Path("C:/config/office/config.json"),
            "tcp://127.0.0.1:52200",
            Path("C:/config/office/daemon.log"),
        )
        with patch("wingman.service.tempfile.gettempdir", return_value=str(tmp_path)):
            xml_file = _write_task_xml("office", parts)

        content = xml_file.read_text(encoding="utf-16")
        assert "<RunLevel>HighestAvailable</RunLevel>" in content
        assert (
            "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>" in content
        )
        assert "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in content
        assert "<Command>powershell.exe</Command>" in content
        assert "<Hidden>true</Hidden>" in content
        assert "netbird" in content
        xml_file.unlink()


class TestWindowsUnregister:
    def test_deletes_scheduled_task_directly(self) -> None:
        from wingman.service import unregister_service

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("wingman.service.sys.platform", "win32"),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            unregister_service("office")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "schtasks"
        assert "/delete" in cmd
        assert "wingman-office" in cmd
        assert "/f" in cmd

    def test_elevates_when_access_denied(self) -> None:
        from wingman.service import unregister_service

        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=1, stderr="access denied"),  # direct delete
                MagicMock(returncode=0),  # _is_registered query -> exists
                MagicMock(returncode=0),  # powershell elevation
            ]
        )
        with (
            patch("wingman.service.sys.platform", "win32"),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            unregister_service("office")

        assert mock_run.call_count == 3
        ps_cmd = mock_run.call_args_list[2][0][0]
        assert ps_cmd[0] == "powershell"
        assert "RunAs" in ps_cmd[2]

    def test_unregister_idempotent(self) -> None:
        from wingman.service import unregister_service

        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=1, stderr="not found"),  # direct delete
                MagicMock(returncode=1),  # _is_registered query -> doesn't exist
            ]
        )
        with (
            patch("wingman.service.sys.platform", "win32"),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            unregister_service("office")  # should not raise

        # Should not attempt elevation since task doesn't exist
        assert mock_run.call_count == 2


class TestWindowsIsRegistered:
    def test_returns_true_when_exists(self) -> None:
        from wingman.service import is_service_registered

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("wingman.service.sys.platform", "win32"),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            assert is_service_registered("office") is True

    def test_returns_false_when_missing(self) -> None:
        from wingman.service import is_service_registered

        mock_run = MagicMock(return_value=MagicMock(returncode=1))
        with (
            patch("wingman.service.sys.platform", "win32"),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            assert is_service_registered("office") is False


class TestLinuxRegister:
    def test_writes_unit_file_and_enables(self, tmp_path: Path) -> None:
        from wingman.service import register_service

        unit_dir = tmp_path / ".config" / "systemd" / "user"
        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        with (
            patch("wingman.service.sys.platform", "linux"),
            patch("wingman.service.os.geteuid", return_value=1000),
            patch("wingman.service.Path.home", return_value=tmp_path),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            register_service(
                name="office",
                netbird_bin="/usr/bin/netbird",
                config_path=Path("/home/user/.config/wingman/office/config.json"),
                daemon_addr="unix:///home/user/.config/wingman/office/office.sock",
                log_file=Path("/home/user/.config/wingman/office/daemon.log"),
                env={"NB_STATE_DIR": "/home/user/.config/wingman/office"},
            )

        unit_file = unit_dir / "wingman-office.service"
        assert unit_file.exists()
        content = unit_file.read_text()
        assert "ExecStart=/usr/bin/netbird service run" in content
        assert (
            "--daemon-addr unix:///home/user/.config/wingman/office/office.sock"
            in content
        )
        assert 'Environment="NB_STATE_DIR=/home/user/.config/wingman/office"' in content
        assert "WantedBy=default.target" in content

        assert mock_run.call_count == 2  # daemon-reload + enable
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert ["systemctl", "--user", "daemon-reload"] in cmds
        assert ["systemctl", "--user", "enable", "wingman-office.service"] in cmds

    def test_register_warns_on_failure(self, tmp_path: Path, capsys) -> None:
        from wingman.service import register_service

        mock_run = MagicMock(
            return_value=MagicMock(returncode=1, stderr="Failed to enable")
        )
        with (
            patch("wingman.service.sys.platform", "linux"),
            patch("wingman.service.os.geteuid", return_value=1000),
            patch("wingman.service.Path.home", return_value=tmp_path),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            register_service(
                name="office",
                netbird_bin="/usr/bin/netbird",
                config_path=Path("/tmp/wingman/office/config.json"),
                daemon_addr="unix:///tmp/office.sock",
                log_file=Path("/tmp/wingman/office/daemon.log"),
            )
        captured = capsys.readouterr()
        assert "Warning" in captured.err


class TestLinuxUnregister:
    def test_disables_and_removes_unit_file(self, tmp_path: Path) -> None:
        from wingman.service import unregister_service

        unit_dir = tmp_path / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True)
        unit_file = unit_dir / "wingman-office.service"
        unit_file.write_text("[Unit]\nDescription=test\n")

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("wingman.service.sys.platform", "linux"),
            patch("wingman.service.os.geteuid", return_value=1000),
            patch("wingman.service.Path.home", return_value=tmp_path),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            unregister_service("office")

        assert not unit_file.exists()
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert ["systemctl", "--user", "disable", "wingman-office.service"] in cmds
        assert ["systemctl", "--user", "daemon-reload"] in cmds

    def test_unregister_idempotent_no_file(self, tmp_path: Path) -> None:
        from wingman.service import unregister_service

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("wingman.service.sys.platform", "linux"),
            patch("wingman.service.os.geteuid", return_value=1000),
            patch("wingman.service.Path.home", return_value=tmp_path),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            unregister_service("office")  # should not raise


class TestLinuxIsRegistered:
    def test_returns_true_when_enabled(self) -> None:
        from wingman.service import is_service_registered

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("wingman.service.sys.platform", "linux"),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            assert is_service_registered("office") is True

    def test_returns_false_when_not_enabled(self) -> None:
        from wingman.service import is_service_registered

        mock_run = MagicMock(return_value=MagicMock(returncode=1))
        with (
            patch("wingman.service.sys.platform", "linux"),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            assert is_service_registered("office") is False


class TestSystemdScope:
    def test_root_uses_system_scope(self) -> None:
        from wingman.service import _systemd_scope

        with patch("wingman.service.os.geteuid", return_value=0):
            unit_dir, systemctl, wanted_by = _systemd_scope()
        assert unit_dir == Path("/etc/systemd/system")
        assert systemctl == ["systemctl"]
        assert wanted_by == "multi-user.target"

    def test_non_root_uses_user_scope(self, tmp_path: Path) -> None:
        from wingman.service import _systemd_scope

        with (
            patch("wingman.service.os.geteuid", return_value=1000),
            patch("wingman.service.Path.home", return_value=tmp_path),
        ):
            unit_dir, systemctl, wanted_by = _systemd_scope()
        assert unit_dir == tmp_path / ".config" / "systemd" / "user"
        assert systemctl == ["systemctl", "--user"]
        assert wanted_by == "default.target"

    def test_root_registers_system_unit(self, tmp_path: Path) -> None:
        from wingman.service import register_service

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        # Redirect the system unit dir so the test never touches real /etc.
        with (
            patch("wingman.service.sys.platform", "linux"),
            patch(
                "wingman.service._systemd_scope",
                return_value=(tmp_path, ["systemctl"], "multi-user.target"),
            ),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            register_service(
                name="office",
                netbird_bin="/usr/bin/netbird",
                config_path=Path("/root/.config/wingman/office/config.json"),
                daemon_addr="unix:///var/run/wingman-office.sock",
                log_file=Path("/root/.config/wingman/office/daemon.log"),
                env={"NB_STATE_DIR": "/root/.config/wingman/office"},
            )

        content = (tmp_path / "wingman-office.service").read_text()
        assert "WantedBy=multi-user.target" in content
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert ["systemctl", "enable", "wingman-office.service"] in cmds


class TestMacosRegister:
    def test_writes_plist_and_loads(self, tmp_path: Path) -> None:
        from wingman.service import register_service

        launch_agents = tmp_path / "Library" / "LaunchAgents"
        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        with (
            patch("wingman.service.sys.platform", "darwin"),
            patch("wingman.service.Path.home", return_value=tmp_path),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            register_service(
                name="office",
                netbird_bin="/usr/local/bin/netbird",
                config_path=Path("/Users/user/.config/wingman/office/config.json"),
                daemon_addr="unix:///Users/user/.config/wingman/office/office.sock",
                log_file=Path("/Users/user/.config/wingman/office/daemon.log"),
            )

        plist = launch_agents / "com.wingman.office.plist"
        assert plist.exists()
        content = plist.read_text()
        assert "<key>Label</key>" in content
        assert "<string>com.wingman.office</string>" in content
        assert "<string>/usr/local/bin/netbird</string>" in content
        assert "<key>RunAtLoad</key>" in content

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "launchctl"
        assert "load" in cmd

    def test_register_warns_on_failure(self, tmp_path: Path, capsys) -> None:
        from wingman.service import register_service

        mock_run = MagicMock(
            return_value=MagicMock(returncode=1, stderr="permission denied")
        )
        with (
            patch("wingman.service.sys.platform", "darwin"),
            patch("wingman.service.Path.home", return_value=tmp_path),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            register_service(
                name="office",
                netbird_bin="/usr/local/bin/netbird",
                config_path=Path("/tmp/wingman/office/config.json"),
                daemon_addr="unix:///tmp/office.sock",
                log_file=Path("/tmp/wingman/office/daemon.log"),
            )
        captured = capsys.readouterr()
        assert "Warning" in captured.err


class TestMacosUnregister:
    def test_unloads_and_removes_plist(self, tmp_path: Path) -> None:
        from wingman.service import unregister_service

        launch_agents = tmp_path / "Library" / "LaunchAgents"
        launch_agents.mkdir(parents=True)
        plist = launch_agents / "com.wingman.office.plist"
        plist.write_text("<plist>test</plist>")

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("wingman.service.sys.platform", "darwin"),
            patch("wingman.service.Path.home", return_value=tmp_path),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            unregister_service("office")

        assert not plist.exists()
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "launchctl"
        assert cmd[1] == "unload"

    def test_unregister_idempotent_no_plist(self, tmp_path: Path) -> None:
        from wingman.service import unregister_service

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("wingman.service.sys.platform", "darwin"),
            patch("wingman.service.Path.home", return_value=tmp_path),
            patch("wingman.service.subprocess.run", mock_run),
        ):
            unregister_service("office")  # should not raise


class TestMacosIsRegistered:
    def test_returns_true_when_plist_exists(self, tmp_path: Path) -> None:
        from wingman.service import is_service_registered

        launch_agents = tmp_path / "Library" / "LaunchAgents"
        launch_agents.mkdir(parents=True)
        (launch_agents / "com.wingman.office.plist").write_text("<plist/>")

        with (
            patch("wingman.service.sys.platform", "darwin"),
            patch("wingman.service.Path.home", return_value=tmp_path),
        ):
            assert is_service_registered("office") is True

    def test_returns_false_when_no_plist(self, tmp_path: Path) -> None:
        from wingman.service import is_service_registered

        with (
            patch("wingman.service.sys.platform", "darwin"),
            patch("wingman.service.Path.home", return_value=tmp_path),
        ):
            assert is_service_registered("office") is False
