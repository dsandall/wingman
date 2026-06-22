from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


class TestWindowsRegister:
    def test_creates_scheduled_task_directly(self, tmp_path: Path) -> None:
        from twinbird.service import register_service

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("twinbird.service.sys.platform", "win32"),
            patch("twinbird.service.subprocess.run", mock_run),
            patch("twinbird.service.tempfile.gettempdir", return_value=str(tmp_path)),
        ):
            register_service(
                name="office",
                netbird_bin="C:/Program Files/netbird/netbird.exe",
                config_path=Path(
                    "C:/Users/user/AppData/Roaming/twinbird/office/config.json"
                ),
                daemon_addr="tcp://127.0.0.1:52200",
                log_file=Path(
                    "C:/Users/user/AppData/Roaming/twinbird/office/daemon.log"
                ),
            )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "schtasks"
        assert "/create" in cmd
        assert "/xml" in cmd
        assert "twinbird-office" in cmd

    def test_elevates_when_access_denied(self, tmp_path: Path) -> None:
        from twinbird.service import register_service

        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=1, stderr="access denied"),  # direct create
                MagicMock(returncode=0),  # powershell elevation
                MagicMock(returncode=0),  # _is_registered query
            ]
        )
        with (
            patch("twinbird.service.sys.platform", "win32"),
            patch("twinbird.service.subprocess.run", mock_run),
            patch("twinbird.service.tempfile.gettempdir", return_value=str(tmp_path)),
        ):
            register_service(
                name="office",
                netbird_bin="netbird",
                config_path=Path(
                    "C:/Users/user/AppData/Roaming/twinbird/office/config.json"
                ),
                daemon_addr="tcp://127.0.0.1:52200",
                log_file=Path(
                    "C:/Users/user/AppData/Roaming/twinbird/office/daemon.log"
                ),
            )

        assert mock_run.call_count == 3
        # Second call should be powershell elevation
        ps_cmd = mock_run.call_args_list[1][0][0]
        assert ps_cmd[0] == "powershell"
        assert "RunAs" in ps_cmd[2]

    def test_register_warns_on_failure(self, tmp_path: Path, capsys) -> None:
        from twinbird.service import register_service

        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=1, stderr="access denied"),  # direct create
                MagicMock(returncode=0),  # powershell elevation
                MagicMock(returncode=1),  # _is_registered query -> still not there
            ]
        )
        with (
            patch("twinbird.service.sys.platform", "win32"),
            patch("twinbird.service.subprocess.run", mock_run),
            patch("twinbird.service.tempfile.gettempdir", return_value=str(tmp_path)),
        ):
            register_service(
                name="office",
                netbird_bin="netbird",
                config_path=Path("/tmp/twinbird/office/config.json"),
                daemon_addr="tcp://127.0.0.1:52200",
                log_file=Path("/tmp/twinbird/office/daemon.log"),
            )
        captured = capsys.readouterr()
        assert "Warning" in captured.err

    def test_xml_contains_highest_run_level(self, tmp_path: Path) -> None:
        from twinbird.service import _build_netbird_cmd, _write_task_xml

        parts = _build_netbird_cmd(
            "netbird",
            Path("C:/config/office/config.json"),
            "tcp://127.0.0.1:52200",
            Path("C:/config/office/daemon.log"),
        )
        with patch("twinbird.service.tempfile.gettempdir", return_value=str(tmp_path)):
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
        from twinbird.service import unregister_service

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("twinbird.service.sys.platform", "win32"),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            unregister_service("office")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "schtasks"
        assert "/delete" in cmd
        assert "twinbird-office" in cmd
        assert "/f" in cmd

    def test_elevates_when_access_denied(self) -> None:
        from twinbird.service import unregister_service

        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=1, stderr="access denied"),  # direct delete
                MagicMock(returncode=0),  # _is_registered query -> exists
                MagicMock(returncode=0),  # powershell elevation
            ]
        )
        with (
            patch("twinbird.service.sys.platform", "win32"),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            unregister_service("office")

        assert mock_run.call_count == 3
        ps_cmd = mock_run.call_args_list[2][0][0]
        assert ps_cmd[0] == "powershell"
        assert "RunAs" in ps_cmd[2]

    def test_unregister_idempotent(self) -> None:
        from twinbird.service import unregister_service

        mock_run = MagicMock(
            side_effect=[
                MagicMock(returncode=1, stderr="not found"),  # direct delete
                MagicMock(returncode=1),  # _is_registered query -> doesn't exist
            ]
        )
        with (
            patch("twinbird.service.sys.platform", "win32"),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            unregister_service("office")  # should not raise

        # Should not attempt elevation since task doesn't exist
        assert mock_run.call_count == 2


class TestWindowsIsRegistered:
    def test_returns_true_when_exists(self) -> None:
        from twinbird.service import is_service_registered

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("twinbird.service.sys.platform", "win32"),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            assert is_service_registered("office") is True

    def test_returns_false_when_missing(self) -> None:
        from twinbird.service import is_service_registered

        mock_run = MagicMock(return_value=MagicMock(returncode=1))
        with (
            patch("twinbird.service.sys.platform", "win32"),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            assert is_service_registered("office") is False


class TestLinuxRegister:
    def test_writes_unit_file_and_enables(self, tmp_path: Path) -> None:
        from twinbird.service import register_service

        unit_dir = tmp_path / ".config" / "systemd" / "user"
        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        with (
            patch("twinbird.service.sys.platform", "linux"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            register_service(
                name="office",
                netbird_bin="/usr/bin/netbird",
                config_path=Path("/home/user/.config/twinbird/office/config.json"),
                daemon_addr="unix:///home/user/.config/twinbird/office/office.sock",
                log_file=Path("/home/user/.config/twinbird/office/daemon.log"),
                env={"NB_STATE_DIR": "/home/user/.config/twinbird/office"},
            )

        unit_file = unit_dir / "twinbird-office.service"
        assert unit_file.exists()
        content = unit_file.read_text()
        assert "ExecStart=/usr/bin/netbird service run" in content
        assert (
            "--daemon-addr unix:///home/user/.config/twinbird/office/office.sock"
            in content
        )
        assert (
            'Environment="NB_STATE_DIR=/home/user/.config/twinbird/office"' in content
        )
        assert "WantedBy=default.target" in content

        assert mock_run.call_count == 2  # daemon-reload + enable
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert ["systemctl", "--user", "daemon-reload"] in cmds
        assert ["systemctl", "--user", "enable", "twinbird-office.service"] in cmds

    def test_register_warns_on_failure(self, tmp_path: Path, capsys) -> None:
        from twinbird.service import register_service

        mock_run = MagicMock(
            return_value=MagicMock(returncode=1, stderr="Failed to enable")
        )
        with (
            patch("twinbird.service.sys.platform", "linux"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            register_service(
                name="office",
                netbird_bin="/usr/bin/netbird",
                config_path=Path("/tmp/twinbird/office/config.json"),
                daemon_addr="unix:///tmp/office.sock",
                log_file=Path("/tmp/twinbird/office/daemon.log"),
            )
        captured = capsys.readouterr()
        assert "Warning" in captured.err


class TestLinuxUnregister:
    def test_disables_and_removes_unit_file(self, tmp_path: Path) -> None:
        from twinbird.service import unregister_service

        unit_dir = tmp_path / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True)
        unit_file = unit_dir / "twinbird-office.service"
        unit_file.write_text("[Unit]\nDescription=test\n")

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("twinbird.service.sys.platform", "linux"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            unregister_service("office")

        assert not unit_file.exists()
        cmds = [c[0][0] for c in mock_run.call_args_list]
        assert ["systemctl", "--user", "disable", "twinbird-office.service"] in cmds
        assert ["systemctl", "--user", "daemon-reload"] in cmds

    def test_unregister_idempotent_no_file(self, tmp_path: Path) -> None:
        from twinbird.service import unregister_service

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("twinbird.service.sys.platform", "linux"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            unregister_service("office")  # should not raise


class TestLinuxIsRegistered:
    def test_returns_true_when_enabled(self) -> None:
        from twinbird.service import is_service_registered

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("twinbird.service.sys.platform", "linux"),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            assert is_service_registered("office") is True

    def test_returns_false_when_not_enabled(self) -> None:
        from twinbird.service import is_service_registered

        mock_run = MagicMock(return_value=MagicMock(returncode=1))
        with (
            patch("twinbird.service.sys.platform", "linux"),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            assert is_service_registered("office") is False


class TestMacosRegister:
    def test_writes_plist_and_loads(self, tmp_path: Path) -> None:
        from twinbird.service import register_service

        launch_agents = tmp_path / "Library" / "LaunchAgents"
        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        with (
            patch("twinbird.service.sys.platform", "darwin"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            register_service(
                name="office",
                netbird_bin="/usr/local/bin/netbird",
                config_path=Path("/Users/user/.config/twinbird/office/config.json"),
                daemon_addr="unix:///Users/user/.config/twinbird/office/office.sock",
                log_file=Path("/Users/user/.config/twinbird/office/daemon.log"),
            )

        plist = launch_agents / "com.twinbird.office.plist"
        assert plist.exists()
        content = plist.read_text()
        assert "<key>Label</key>" in content
        assert "<string>com.twinbird.office</string>" in content
        assert "<string>/usr/local/bin/netbird</string>" in content
        assert "<key>RunAtLoad</key>" in content

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "launchctl"
        assert "load" in cmd

    def test_register_warns_on_failure(self, tmp_path: Path, capsys) -> None:
        from twinbird.service import register_service

        mock_run = MagicMock(
            return_value=MagicMock(returncode=1, stderr="permission denied")
        )
        with (
            patch("twinbird.service.sys.platform", "darwin"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            register_service(
                name="office",
                netbird_bin="/usr/local/bin/netbird",
                config_path=Path("/tmp/twinbird/office/config.json"),
                daemon_addr="unix:///tmp/office.sock",
                log_file=Path("/tmp/twinbird/office/daemon.log"),
            )
        captured = capsys.readouterr()
        assert "Warning" in captured.err


class TestMacosUnregister:
    def test_unloads_and_removes_plist(self, tmp_path: Path) -> None:
        from twinbird.service import unregister_service

        launch_agents = tmp_path / "Library" / "LaunchAgents"
        launch_agents.mkdir(parents=True)
        plist = launch_agents / "com.twinbird.office.plist"
        plist.write_text("<plist>test</plist>")

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("twinbird.service.sys.platform", "darwin"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            unregister_service("office")

        assert not plist.exists()
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "launchctl"
        assert cmd[1] == "unload"

    def test_unregister_idempotent_no_plist(self, tmp_path: Path) -> None:
        from twinbird.service import unregister_service

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with (
            patch("twinbird.service.sys.platform", "darwin"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
            patch("twinbird.service.subprocess.run", mock_run),
        ):
            unregister_service("office")  # should not raise


class TestMacosIsRegistered:
    def test_returns_true_when_plist_exists(self, tmp_path: Path) -> None:
        from twinbird.service import is_service_registered

        launch_agents = tmp_path / "Library" / "LaunchAgents"
        launch_agents.mkdir(parents=True)
        (launch_agents / "com.twinbird.office.plist").write_text("<plist/>")

        with (
            patch("twinbird.service.sys.platform", "darwin"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
        ):
            assert is_service_registered("office") is True

    def test_returns_false_when_no_plist(self, tmp_path: Path) -> None:
        from twinbird.service import is_service_registered

        with (
            patch("twinbird.service.sys.platform", "darwin"),
            patch("twinbird.service.Path.home", return_value=tmp_path),
        ):
            assert is_service_registered("office") is False
