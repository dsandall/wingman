from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from twinbird.config import (
    InstanceMetadata,
    ensure_instance_dir,
    read_metadata,
    write_metadata,
    write_pid,
)
from twinbird.platform import PlatformConfig


def _mock_platform(tmp_path: Path) -> PlatformConfig:
    return PlatformConfig(config_root=tmp_path, interface_prefix="wt")


def _mock_runtime(tmp_path: Path, name: str) -> tuple[Path, dict[str, str]]:
    return tmp_path / name / "config.json", {}


class TestUp:
    def test_starts_and_connects(self, tmp_path: Path) -> None:
        from twinbird.instance import up

        platform = _mock_platform(tmp_path)

        with (
            patch("twinbird.instance.get_platform_config", return_value=platform),
            patch("twinbird.instance.find_netbird_bin", return_value="netbird"),
            patch("twinbird.instance.start_daemon", return_value=42),
            patch("twinbird.instance.read_pid", return_value=None),
            patch(
                "twinbird.instance.run_up",
                return_value=MagicMock(returncode=0, stdout="Connected"),
            ),
            patch(
                "twinbird.instance.derive_daemon_addr",
                return_value="tcp://127.0.0.1:52200",
            ),
            patch("twinbird.instance.derive_interface_name", return_value="wt7"),
            patch(
                "twinbird.instance.derive_netbird_runtime",
                return_value=_mock_runtime(tmp_path, "office"),
            ),
            patch("twinbird.instance.register_service"),
        ):
            up(
                name="office",
                management_url="https://mgmt.example.com",
                setup_key="KEY123",
            )

        metadata = read_metadata(tmp_path, "office")
        assert metadata is not None
        assert metadata.name == "office"
        assert metadata.pid == 42

    def test_already_running(self, tmp_path: Path, capsys) -> None:
        from twinbird.instance import up

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        write_pid(tmp_path, "office", 42)
        meta = InstanceMetadata(
            "office", "url", "addr", "wt7", 42, "t", service_registered=True
        )
        write_metadata(tmp_path, meta)

        with (
            patch("twinbird.instance.get_platform_config", return_value=platform),
            patch("twinbird.instance.find_netbird_bin", return_value="netbird"),
            patch("twinbird.instance.is_process_alive", return_value=True),
            patch("twinbird.instance.read_pid", return_value=42),
            patch("twinbird.instance.is_service_registered", return_value=True),
            patch(
                "twinbird.instance.derive_netbird_runtime",
                return_value=_mock_runtime(tmp_path, "office"),
            ),
        ):
            up(
                name="office",
                management_url="https://mgmt.example.com",
                setup_key="KEY123",
            )

        captured = capsys.readouterr()
        assert "already running" in captured.out

    def test_already_running_registers_missing_service(
        self, tmp_path: Path, capsys
    ) -> None:
        from twinbird.instance import up

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        write_pid(tmp_path, "office", 42)
        meta = InstanceMetadata(
            "office", "url", "addr", "wt7", 42, "t", service_registered=False
        )
        write_metadata(tmp_path, meta)
        mock_register = MagicMock()

        with (
            patch("twinbird.instance.get_platform_config", return_value=platform),
            patch("twinbird.instance.find_netbird_bin", return_value="netbird"),
            patch("twinbird.instance.is_process_alive", return_value=True),
            patch("twinbird.instance.read_pid", return_value=42),
            patch("twinbird.instance.is_service_registered", return_value=False),
            patch(
                "twinbird.instance.derive_netbird_runtime",
                return_value=_mock_runtime(tmp_path, "office"),
            ),
            patch("twinbird.instance.register_service", mock_register),
        ):
            up(
                name="office",
                management_url="https://mgmt.example.com",
                setup_key="KEY123",
            )

        mock_register.assert_called_once()
        captured = capsys.readouterr()
        assert "already running" in captured.out
        updated = read_metadata(tmp_path, "office")
        assert updated is not None
        assert updated.service_registered is True

    def test_registers_service_on_up(self, tmp_path: Path) -> None:
        from twinbird.instance import up

        platform = _mock_platform(tmp_path)
        mock_register = MagicMock()

        with (
            patch("twinbird.instance.get_platform_config", return_value=platform),
            patch("twinbird.instance.find_netbird_bin", return_value="netbird"),
            patch("twinbird.instance.start_daemon", return_value=42),
            patch("twinbird.instance.read_pid", return_value=None),
            patch(
                "twinbird.instance.run_up",
                return_value=MagicMock(returncode=0, stdout="Connected"),
            ),
            patch(
                "twinbird.instance.derive_daemon_addr",
                return_value="tcp://127.0.0.1:52200",
            ),
            patch("twinbird.instance.derive_interface_name", return_value="wt7"),
            patch(
                "twinbird.instance.derive_netbird_runtime",
                return_value=_mock_runtime(tmp_path, "office"),
            ),
            patch("twinbird.instance.register_service", mock_register),
        ):
            up(
                name="office",
                management_url="https://mgmt.example.com",
                setup_key="KEY123",
            )

        mock_register.assert_called_once_with(
            name="office",
            netbird_bin="netbird",
            config_path=tmp_path / "office" / "config.json",
            daemon_addr="tcp://127.0.0.1:52200",
            log_file=tmp_path / "office" / "daemon.log",
            env={},
        )

        metadata = read_metadata(tmp_path, "office")
        assert metadata is not None
        assert metadata.service_registered is True


class TestDown:
    def test_stops_instance(self, tmp_path: Path) -> None:
        from twinbird.instance import down

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office", "url", "tcp://127.0.0.1:52200", "wt7", 42, "t"
        )
        write_metadata(tmp_path, meta)
        write_pid(tmp_path, "office", 42)

        with (
            patch("twinbird.instance.get_platform_config", return_value=platform),
            patch("twinbird.instance.find_netbird_bin", return_value="netbird"),
            patch("twinbird.instance.read_pid", return_value=42),
            patch("twinbird.instance.is_process_alive", return_value=True),
            patch("twinbird.instance.run_down", return_value=MagicMock(returncode=0)),
            patch("twinbird.instance.stop_daemon"),
            patch("twinbird.instance.unregister_service"),
        ):
            down("office")

    def test_not_found(self, tmp_path: Path) -> None:
        from twinbird.instance import down

        platform = _mock_platform(tmp_path)

        import click

        with patch("twinbird.instance.get_platform_config", return_value=platform):
            try:
                down("nonexistent")
                raise AssertionError("Should have raised SystemExit")
            except (SystemExit, click.exceptions.Exit):
                pass

    def test_unregisters_service_on_down(self, tmp_path: Path) -> None:
        from twinbird.instance import down

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office",
            "url",
            "tcp://127.0.0.1:52200",
            "wt7",
            42,
            "t",
            service_registered=True,
        )
        write_metadata(tmp_path, meta)
        write_pid(tmp_path, "office", 42)
        mock_unregister = MagicMock()

        with (
            patch("twinbird.instance.get_platform_config", return_value=platform),
            patch("twinbird.instance.find_netbird_bin", return_value="netbird"),
            patch("twinbird.instance.read_pid", return_value=42),
            patch("twinbird.instance.is_process_alive", return_value=True),
            patch("twinbird.instance.run_down", return_value=MagicMock(returncode=0)),
            patch("twinbird.instance.stop_daemon"),
            patch("twinbird.instance.unregister_service", mock_unregister),
        ):
            down("office")

        mock_unregister.assert_called_once_with("office")

    def test_unregisters_service_on_stale_pid(self, tmp_path: Path) -> None:
        from twinbird.instance import down

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office",
            "url",
            "tcp://127.0.0.1:52200",
            "wt7",
            42,
            "t",
            service_registered=True,
        )
        write_metadata(tmp_path, meta)
        write_pid(tmp_path, "office", 42)
        mock_unregister = MagicMock()

        with (
            patch("twinbird.instance.get_platform_config", return_value=platform),
            patch("twinbird.instance.find_netbird_bin", return_value="netbird"),
            patch("twinbird.instance.read_pid", return_value=42),
            patch("twinbird.instance.is_process_alive", return_value=False),
            patch("twinbird.instance.unregister_service", mock_unregister),
        ):
            down("office")

        mock_unregister.assert_called_once_with("office")


class TestListAll:
    def test_no_instances(self, tmp_path: Path, capsys) -> None:
        from twinbird.instance import list_all

        platform = _mock_platform(tmp_path)

        with patch("twinbird.instance.get_platform_config", return_value=platform):
            list_all()

        captured = capsys.readouterr()
        assert "No instances found" in captured.out

    def test_shows_persistent_label(self, tmp_path: Path, capsys) -> None:
        from twinbird.instance import list_all

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office", "url", "addr", "wt7", 42, "t", service_registered=True
        )
        write_metadata(tmp_path, meta)
        write_pid(tmp_path, "office", 42)

        with (
            patch("twinbird.instance.get_platform_config", return_value=platform),
            patch("twinbird.instance.is_process_alive", return_value=True),
            patch("twinbird.instance.is_service_registered", return_value=True),
        ):
            list_all()

        captured = capsys.readouterr()
        assert "office: running (persistent)" in captured.out

    def test_shows_running_without_persistent(self, tmp_path: Path, capsys) -> None:
        from twinbird.instance import list_all

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office", "url", "addr", "wt7", 42, "t", service_registered=False
        )
        write_metadata(tmp_path, meta)
        write_pid(tmp_path, "office", 42)

        with (
            patch("twinbird.instance.get_platform_config", return_value=platform),
            patch("twinbird.instance.is_process_alive", return_value=True),
            patch("twinbird.instance.is_service_registered", return_value=False),
        ):
            list_all()

        captured = capsys.readouterr()
        assert "office: running" in captured.out
        assert "persistent" not in captured.out


class TestParsePeerLines:
    def test_parses_name_and_status(self) -> None:
        from twinbird.instance import _parse_peer_lines

        detail = """Peers detail:
 lynx.netbird.cloud:
  NetBird IP: 100.64.135.69
  Status: Connected
 cubert.netbird.cloud:
  NetBird IP: 100.64.18.8
  Status: Idle
"""
        assert _parse_peer_lines(detail) == [
            ("lynx", "Connected"),
            ("cubert", "Idle"),
        ]

    def test_domain_agnostic_short_name(self) -> None:
        from twinbird.instance import _parse_peer_lines

        detail = " host-a.netbird.example.com:\n  Status: Connected\n"
        assert _parse_peer_lines(detail) == [("host-a", "Connected")]

    def test_no_peers(self) -> None:
        from twinbird.instance import _parse_peer_lines

        assert _parse_peer_lines("Peers count: 0/0 Connected\n") == []
