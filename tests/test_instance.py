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
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.start_daemon", return_value=42),
            patch("wingman.instance.read_pid", return_value=None),
            patch("wingman.instance.is_service_active", return_value=False),
            patch("wingman.instance.start_service", return_value=True),
            patch("wingman.instance._wait_daemon_ready", return_value=True),
            patch("wingman.instance.service_main_pid", return_value=42),
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

    def test_managed_start_uses_systemd_not_direct_daemon(self, tmp_path: Path) -> None:
        from wingman.instance import up

        platform = _mock_platform(tmp_path)
        mock_start_daemon = MagicMock(return_value=99)
        mock_start_service = MagicMock(return_value=True)

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.read_pid", return_value=None),
            patch("wingman.instance.is_service_active", return_value=False),
            patch("wingman.instance.register_service"),
            patch("wingman.instance.start_service", mock_start_service),
            patch("wingman.instance._wait_daemon_ready", return_value=True),
            patch("wingman.instance.service_main_pid", return_value=1234),
            patch("wingman.instance.start_daemon", mock_start_daemon),
            patch(
                "wingman.instance.run_up",
                return_value=MagicMock(returncode=0, stdout="Connected"),
            ),
            patch(
                "wingman.instance.derive_daemon_addr",
                return_value="unix:///tmp/office.sock",
            ),
            patch("wingman.instance.derive_interface_name", return_value="wt7"),
            patch(
                "wingman.instance.derive_netbird_runtime",
                return_value=_mock_runtime(tmp_path, "office"),
            ),
        ):
            up(name="office", management_url="https://m", setup_key="K")

        mock_start_service.assert_called_once_with("office")
        mock_start_daemon.assert_not_called()  # systemd owns the process
        metadata = read_metadata(tmp_path, "office")
        assert metadata is not None
        assert metadata.pid == 1234  # systemd MainPID, not a direct PID

    def test_falls_back_to_direct_daemon_without_systemd(self, tmp_path: Path) -> None:
        from wingman.instance import up

        platform = _mock_platform(tmp_path)
        mock_start_daemon = MagicMock(return_value=77)

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.read_pid", return_value=None),
            patch("wingman.instance.is_service_active", return_value=False),
            patch("wingman.instance.register_service"),
            patch("wingman.instance.start_service", return_value=None),
            patch("wingman.instance.start_daemon", mock_start_daemon),
            patch(
                "wingman.instance.run_up",
                return_value=MagicMock(returncode=0, stdout="Connected"),
            ),
            patch(
                "wingman.instance.derive_daemon_addr",
                return_value="unix:///tmp/office.sock",
            ),
            patch("wingman.instance.derive_interface_name", return_value="wt7"),
            patch(
                "wingman.instance.derive_netbird_runtime",
                return_value=_mock_runtime(tmp_path, "office"),
            ),
        ):
            up(name="office", management_url="https://m", setup_key="K")

        mock_start_daemon.assert_called_once()  # no systemd → supervise directly
        metadata = read_metadata(tmp_path, "office")
        assert metadata is not None
        assert metadata.pid == 77

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
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.is_service_active", return_value=False),
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
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.is_service_active", return_value=False),
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
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.start_daemon", return_value=42),
            patch("wingman.instance.read_pid", return_value=None),
            patch("wingman.instance.is_service_active", return_value=False),
            patch("wingman.instance.start_service", return_value=True),
            patch("wingman.instance._wait_daemon_ready", return_value=True),
            patch("wingman.instance.service_main_pid", return_value=42),
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
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.is_service_active", return_value=False),
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
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.is_service_active", return_value=False),
            patch("wingman.instance.read_pid", return_value=42),
            patch("wingman.instance.is_process_alive", return_value=True),
            patch("wingman.instance.run_down", return_value=MagicMock(returncode=0)),
            patch("wingman.instance.stop_daemon"),
            patch("wingman.instance.unregister_service", mock_unregister),
        ):
            down("office")

        mock_unregister.assert_called_once_with("office")

    def test_stops_systemd_service_when_active(self, tmp_path: Path) -> None:
        from wingman.instance import down

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office",
            "url",
            "unix:///tmp/office.sock",
            "wt7",
            0,
            "t",
            service_registered=True,
        )
        write_metadata(tmp_path, meta)
        mock_stop_service = MagicMock()
        mock_stop_daemon = MagicMock()

        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.find_netbird_bin", return_value="netbird"),
            patch("wingman.instance.has_net_admin_capability", return_value=None),
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.is_service_active", return_value=True),
            patch("wingman.instance.read_pid", return_value=None),
            patch("wingman.instance.run_down", return_value=MagicMock(returncode=0)),
            patch("wingman.instance.stop_service", mock_stop_service),
            patch("wingman.instance.stop_daemon", mock_stop_daemon),
            patch("wingman.instance.unregister_service"),
        ):
            down("office")

        mock_stop_service.assert_called_once_with("office")
        mock_stop_daemon.assert_not_called()  # no supervised PID to kill

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
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
            patch("wingman.instance.is_service_active", return_value=False),
            patch("wingman.instance.read_pid", return_value=42),
            patch("wingman.instance.is_process_alive", return_value=False),
            patch("wingman.instance.run_down", return_value=MagicMock(returncode=0)),
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
            patch("wingman.instance.is_service_active", return_value=False),
            patch("wingman.instance.is_process_alive", return_value=True),
            patch("wingman.instance.is_service_registered", return_value=True),
        ):
            list_all()

        captured = capsys.readouterr()
        assert "office: running (persistent)" in captured.out

    def test_systemd_active_counts_as_running_without_pid(
        self, tmp_path: Path, capsys
    ) -> None:
        from wingman.instance import list_all

        platform = _mock_platform(tmp_path)
        ensure_instance_dir(tmp_path, "office")
        meta = InstanceMetadata(
            "office",
            "url",
            "unix:///tmp/office.sock",
            "wt7",
            0,
            "t",
            service_registered=True,
        )
        write_metadata(tmp_path, meta)
        # No PID file — systemd owns the process.
        with (
            patch("wingman.instance.get_platform_config", return_value=platform),
            patch("wingman.instance.is_service_active", return_value=True),
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
            patch("wingman.instance.is_service_active", return_value=False),
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
            ("lynx", "Connected", "100.64.135.69"),
            ("cubert", "Idle", "100.64.18.8"),
        ]

    def test_domain_agnostic_short_name(self) -> None:
        from wingman.instance import _parse_peer_lines

        detail = " host-a.netbird.example.com:\n  Status: Connected\n"
        assert _parse_peer_lines(detail) == [("host-a", "Connected", None)]

    def test_ip_absent_when_block_omits_it(self) -> None:
        from wingman.instance import _parse_peer_lines

        detail = " host-a.netbird.cloud:\n  Status: Connected\n"
        assert _parse_peer_lines(detail) == [("host-a", "Connected", None)]

    def test_no_peers(self) -> None:
        from wingman.instance import _parse_peer_lines

        assert _parse_peer_lines("Peers count: 0/0 Connected\n") == []


class TestParseSelfIdentity:
    def test_parses_name_and_strips_cidr(self) -> None:
        from wingman.instance import _parse_self_identity

        status = (
            "Profile: personal\n"
            "FQDN: ice-cubed-155-250.netbird.cloud\n"
            "NetBird IP: 100.81.155.250/16\n"
            "Peers count: 2/3 Connected\n"
        )
        assert _parse_self_identity(status) == ("ice-cubed-155-250", "100.81.155.250")

    def test_missing_fields_are_none(self) -> None:
        from wingman.instance import _parse_self_identity

        assert _parse_self_identity("Management: Connected\n") == (None, None)

    def test_ignores_indented_peer_ip_lines(self) -> None:
        from wingman.instance import _parse_self_identity

        # Indented "NetBird IP:" belongs to a peer block, not self.
        status = "FQDN: host.netbird.cloud\n  NetBird IP: 100.64.0.9\n"
        assert _parse_self_identity(status) == ("host", None)


class TestPeerOrdering:
    def test_connected_then_connecting_then_rest(self) -> None:
        from wingman.instance import _peer_sort_key

        peers = [
            ("zeta", "Idle", None),
            ("bravo", "Connected", None),
            ("yankee", "Connecting", None),
            ("alpha", "Connected", None),
            ("mike", "Disconnected", None),
        ]
        ordered = [name for name, _status, _ip in sorted(peers, key=_peer_sort_key)]
        # Connected (alphabetical), then Connecting, then the rest (alphabetical).
        assert ordered == ["alpha", "bravo", "yankee", "mike", "zeta"]

    def test_status_colors(self) -> None:
        from wingman.instance import _STATUS_STYLE

        assert _STATUS_STYLE["connected"] == "green"
        assert _STATUS_STYLE["connecting"] == "yellow"
        # Offline statuses (Idle/Disconnected) are absent → rendered uncolored.
        assert "idle" not in _STATUS_STYLE
        assert "disconnected" not in _STATUS_STYLE


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
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
        ):
            _require_kernel_iface_capability("netbird")  # must not raise


class TestWarnDnsUnavailable:
    def test_warns_when_polkit_unauthorized(self, capsys) -> None:
        from wingman.instance import _warn_dns_unavailable

        with (
            patch("wingman.instance.is_root", return_value=False),
            patch("wingman.instance.resolved_dns_authorized", return_value=False),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
        ):
            _warn_dns_unavailable("netbird")  # must not raise — warning only

        err = capsys.readouterr().err
        assert "polkit" in err
        assert "resolve1.set-" in err
        assert "setcap" not in err  # bind capability is fine

    def test_warns_when_bind_capability_missing(self, capsys) -> None:
        from wingman.instance import _warn_dns_unavailable

        with (
            patch("wingman.instance.is_root", return_value=False),
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=False),
        ):
            _warn_dns_unavailable("netbird")

        err = capsys.readouterr().err
        assert "cap_net_bind_service" in err
        assert "port 53" in err
        assert "polkit" not in err  # polkit is fine

    def test_warns_about_both(self, capsys) -> None:
        from wingman.instance import _warn_dns_unavailable

        with (
            patch("wingman.instance.is_root", return_value=False),
            patch("wingman.instance.resolved_dns_authorized", return_value=False),
            patch("wingman.instance.has_net_bind_capability", return_value=False),
        ):
            _warn_dns_unavailable("netbird")

        err = capsys.readouterr().err
        assert "polkit" in err
        assert "cap_net_bind_service" in err

    def test_silent_when_both_ok(self, capsys) -> None:
        from wingman.instance import _warn_dns_unavailable

        with (
            patch("wingman.instance.is_root", return_value=False),
            patch("wingman.instance.resolved_dns_authorized", return_value=True),
            patch("wingman.instance.has_net_bind_capability", return_value=True),
        ):
            _warn_dns_unavailable("netbird")

        assert capsys.readouterr().err == ""

    def test_silent_when_undeterminable(self, capsys) -> None:
        from wingman.instance import _warn_dns_unavailable

        # None (e.g. no getcap/pkcheck) is not treated as missing.
        with (
            patch("wingman.instance.is_root", return_value=False),
            patch("wingman.instance.resolved_dns_authorized", return_value=None),
            patch("wingman.instance.has_net_bind_capability", return_value=None),
        ):
            _warn_dns_unavailable("netbird")

        assert capsys.readouterr().err == ""

    def test_silent_for_root(self, capsys) -> None:
        from wingman.instance import _warn_dns_unavailable

        # Root bypasses polkit and binds 53 fine — never probe, never warn.
        with (
            patch("wingman.instance.is_root", return_value=True),
            patch(
                "wingman.instance.resolved_dns_authorized",
                side_effect=AssertionError("should not probe as root"),
            ),
            patch(
                "wingman.instance.has_net_bind_capability",
                side_effect=AssertionError("should not probe as root"),
            ),
        ):
            _warn_dns_unavailable("netbird")

        assert capsys.readouterr().err == ""
