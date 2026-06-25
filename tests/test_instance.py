from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from wingman.config import (
    InstanceMetadata,
    ensure_instance_dir,
    read_metadata,
    write_metadata,
    write_pid,
)
from wingman.platform import PlatformConfig


def _mock_platform(tmp_path: Path) -> PlatformConfig:
    return PlatformConfig(config_root=tmp_path, interface_prefix="wt")


def _mock_runtime(tmp_path: Path, name: str) -> tuple[Path, dict[str, str]]:
    return tmp_path / name / "config.json", {}


class TestUp:
    def test_starts_and_connects(self, tmp_path: Path) -> None:
        from wingman.instance import up

        platform = _mock_platform(tmp_path)

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.start_daemon", return_value=42),
            patch("wingman.instance.read_pid", return_value=None),
            patch(
                "wingman.instance.run_up",
                return_value=MagicMock(returncode=0, stdout="Connected"),
            ),
            patch(
                "wingman.instance.derive_daemon_addr",
                return_value="tcp://127.0.0.1:52200",
            ),
            patch("wingman.instance.derive_interface_name", return_value="wt7"),
            patch(
                "wingman.instance.derive_netbird_runtime",
                return_value=_mock_runtime(tmp_path, "office"),
            ),
            patch("wingman.instance.register_service"),
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
        from wingman.instance import up

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        write_pid(tmp_path, "office", 42)
        meta = InstanceMetadata(
            "office", "url", "addr", "wt7", 42, "t", service_registered=True
        )
        write_metadata(tmp_path, meta)

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.is_process_alive", return_value=True),
            patch("wingman.instance.read_pid", return_value=42),
            patch("wingman.instance.is_service_registered", return_value=True),
            patch(
                "wingman.instance.derive_netbird_runtime",
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
        from wingman.instance import up

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        write_pid(tmp_path, "office", 42)
        meta = InstanceMetadata(
            "office", "url", "addr", "wt7", 42, "t", service_registered=False
        )
        write_metadata(tmp_path, meta)
        mock_register = MagicMock()

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.is_process_alive", return_value=True),
            patch("wingman.instance.read_pid", return_value=42),
            patch("wingman.instance.is_service_registered", return_value=False),
            patch(
                "wingman.instance.derive_netbird_runtime",
                return_value=_mock_runtime(tmp_path, "office"),
            ),
            patch("wingman.instance.register_service", mock_register),
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
        from wingman.instance import up

        platform = _mock_platform(tmp_path)
        mock_register = MagicMock()

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.start_daemon", return_value=42),
            patch("wingman.instance.read_pid", return_value=None),
            patch(
                "wingman.instance.run_up",
                return_value=MagicMock(returncode=0, stdout="Connected"),
            ),
            patch(
                "wingman.instance.derive_daemon_addr",
                return_value="tcp://127.0.0.1:52200",
            ),
            patch("wingman.instance.derive_interface_name", return_value="wt7"),
            patch(
                "wingman.instance.derive_netbird_runtime",
                return_value=_mock_runtime(tmp_path, "office"),
            ),
            patch("wingman.instance.register_service", mock_register),
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
        from wingman.instance import down

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office", "url", "tcp://127.0.0.1:52200", "wt7", 42, "t"
        )
        write_metadata(tmp_path, meta)
        write_pid(tmp_path, "office", 42)

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.read_pid", return_value=42),
            patch("wingman.instance.is_process_alive", return_value=True),
            patch("wingman.instance.run_down", return_value=MagicMock(returncode=0)),
            patch("wingman.instance.stop_daemon"),
            patch("wingman.instance.unregister_service"),
        ):
            down("office")

    def test_not_found(self, tmp_path: Path) -> None:
        import typer

        from wingman.instance import down

        platform = _mock_platform(tmp_path)

        with patch("wingman.instance.get_platform_config", return_value=platform):
            try:
                down("nonexistent")
                raise AssertionError("Should have raised typer.Exit")
            except (SystemExit, typer.Exit):
                pass

    def test_unregisters_service_on_down(self, tmp_path: Path) -> None:
        from wingman.instance import down

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
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.read_pid", return_value=42),
            patch("wingman.instance.is_process_alive", return_value=True),
            patch("wingman.instance.run_down", return_value=MagicMock(returncode=0)),
            patch("wingman.instance.stop_daemon"),
            patch("wingman.instance.unregister_service", mock_unregister),
        ):
            down("office")

        mock_unregister.assert_called_once_with("office")

    def test_unregisters_service_on_stale_pid(self, tmp_path: Path) -> None:
        from wingman.instance import down

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
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.read_pid", return_value=42),
            patch("wingman.instance.is_process_alive", return_value=False),
            patch("wingman.instance.unregister_service", mock_unregister),
        ):
            down("office")

        mock_unregister.assert_called_once_with("office")


class TestListAll:
    def test_no_instances(self, tmp_path: Path, capsys) -> None:
        from wingman.instance import list_all

        platform = _mock_platform(tmp_path)

        with patch("wingman.instance.get_platform_config", return_value=platform):
            list_all()

        captured = capsys.readouterr()
        assert "No instances found" in captured.out

    def test_shows_persistent_label(self, tmp_path: Path, capsys) -> None:
        from wingman.instance import list_all

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office", "url", "addr", "wt7", 42, "t", service_registered=True
        )
        write_metadata(tmp_path, meta)
        write_pid(tmp_path, "office", 42)

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.is_process_alive", return_value=True),
            patch("wingman.instance.is_service_registered", return_value=True),
        ):
            list_all()

        captured = capsys.readouterr()
        assert "office: running (persistent)" in captured.out

    def test_shows_running_without_persistent(self, tmp_path: Path, capsys) -> None:
        from wingman.instance import list_all

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office", "url", "addr", "wt7", 42, "t", service_registered=False
        )
        write_metadata(tmp_path, meta)
        write_pid(tmp_path, "office", 42)

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.is_process_alive", return_value=True),
            patch("wingman.instance.is_service_registered", return_value=False),
        ):
            list_all()

        captured = capsys.readouterr()
        assert "office: running" in captured.out
        assert "persistent" not in captured.out


class TestParsePeerLines:
    def test_parses_name_and_status(self) -> None:
        from wingman.instance import _parse_peer_lines

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
        from wingman.instance import _parse_peer_lines

        detail = " host-a.netbird.example.com:\n  Status: Connected\n"
        assert _parse_peer_lines(detail) == [("host-a", "Connected")]

    def test_no_peers(self) -> None:
        from wingman.instance import _parse_peer_lines

        assert _parse_peer_lines("Peers count: 0/0 Connected\n") == []


class TestPeerOrdering:
    def test_connected_then_connecting_then_rest(self) -> None:
        from wingman.instance import _peer_sort_key

        peers = [
            ("zeta", "Idle"),
            ("bravo", "Connected"),
            ("yankee", "Connecting"),
            ("alpha", "Connected"),
            ("mike", "Disconnected"),
        ]
        ordered = [name for name, _ in sorted(peers, key=_peer_sort_key)]
        # Connected (alphabetical), then Connecting, then the rest (alphabetical).
        assert ordered == ["alpha", "bravo", "yankee", "mike", "zeta"]

    def test_status_colors(self) -> None:
        import typer

        from wingman.instance import _styled_status

        assert _styled_status("Connected") == typer.style(
            "Connected", fg=typer.colors.GREEN
        )
        assert _styled_status("Connecting") == typer.style(
            "Connecting", fg=typer.colors.YELLOW
        )
        # Offline statuses are left uncolored.
        assert _styled_status("Idle") == "Idle"
        assert _styled_status("Disconnected") == "Disconnected"


class TestRequireKernelIfaceCapability:
    def test_blocks_rootless_without_capability(self) -> None:
        import typer

        from wingman.instance import _require_kernel_iface_capability

        with (
            patch("wingman.instance.is_root", return_value=False),
            patch("wingman.instance.has_net_admin_capability", return_value=False),
        ):
            try:
                _require_kernel_iface_capability("netbird")
                raise AssertionError("expected typer.Exit")
            except typer.Exit:
                pass

    def test_allows_root(self) -> None:
        from wingman.instance import _require_kernel_iface_capability

        with patch("wingman.instance.is_root", return_value=True):
            _require_kernel_iface_capability("netbird")  # must not raise

    def test_allows_when_undeterminable(self) -> None:
        from wingman.instance import _require_kernel_iface_capability

        with (
            patch("wingman.instance.is_root", return_value=False),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
        ):
            _require_kernel_iface_capability("netbird")  # must not raise
