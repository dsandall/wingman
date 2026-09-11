from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from wingman.platform import (
    PlatformConfig,
    derive_daemon_addr,
    derive_interface_name,
    derive_netbird_runtime,
    get_platform_config,
)


class TestGetPlatformConfig:
    def test_linux_defaults(self) -> None:
        with (
            patch("wingman.platform.sys.platform", "linux"),
            patch("wingman.platform.Path.home", return_value=Path("/home/user")),
            patch.dict("os.environ", {}, clear=True),
        ):
            config = get_platform_config()
            assert config.config_root == Path("/home/user/.config/wingman")
            assert config.interface_prefix == "wt"

    def test_windows_defaults(self) -> None:
        with (
            patch("wingman.platform.sys.platform", "win32"),
            patch.dict(
                "os.environ",
                {"APPDATA": "C:/Users/user/AppData/Roaming"},
                clear=True,
            ),
        ):
            config = get_platform_config()
            assert config.config_root == Path("C:/Users/user/AppData/Roaming/wingman")
            assert config.interface_prefix == "wt"

    def test_darwin_defaults(self) -> None:
        with (
            patch("wingman.platform.sys.platform", "darwin"),
            patch("wingman.platform.Path.home", return_value=Path("/Users/user")),
            patch.dict("os.environ", {}, clear=True),
        ):
            config = get_platform_config()
            assert config.config_root == Path("/Users/user/.config/wingman")
            assert config.interface_prefix == "utun"

    def test_env_override(self) -> None:
        with (
            patch("wingman.platform.sys.platform", "linux"),
            patch.dict("os.environ", {"WINGMAN_CONFIG_DIR": "/custom/path"}),
        ):
            config = get_platform_config()
            assert config.config_root == Path("/custom/path")


class TestDeriveDaemonAddr:
    def test_windows_tcp(self) -> None:
        config = PlatformConfig(
            config_root=Path("C:/Users/user/AppData/wingman"),
            interface_prefix="wt",
        )
        with patch("wingman.platform.sys.platform", "win32"):
            addr = derive_daemon_addr("office", config)
            assert addr.startswith("tcp://127.0.0.1:")
            port = int(addr.split(":")[-1])
            assert 52160 <= port <= 52959

    def test_deterministic(self) -> None:
        config = PlatformConfig(
            config_root=Path("/home/user/.config/wingman"),
            interface_prefix="wt",
        )
        with patch("wingman.platform.sys.platform", "win32"):
            assert derive_daemon_addr("office", config) == derive_daemon_addr(
                "office", config
            )

    def test_different_names_different_addrs(self) -> None:
        config = PlatformConfig(
            config_root=Path("/home/user/.config/wingman"),
            interface_prefix="wt",
        )
        with patch("wingman.platform.sys.platform", "win32"):
            assert derive_daemon_addr("office", config) != derive_daemon_addr(
                "home", config
            )

    def test_linux_root(self) -> None:
        config = PlatformConfig(
            config_root=Path("/home/user/.config/wingman"),
            interface_prefix="wt",
        )
        with (
            patch("wingman.platform.sys.platform", "linux"),
            patch("wingman.platform._is_root", return_value=True),
        ):
            addr = derive_daemon_addr("office", config)
            assert addr == "unix:///var/run/wingman-office.sock"

    def test_linux_non_root(self) -> None:
        config = PlatformConfig(
            config_root=Path("/home/user/.config/wingman"),
            interface_prefix="wt",
        )
        with (
            patch("wingman.platform.sys.platform", "linux"),
            patch("wingman.platform._is_root", return_value=False),
        ):
            addr = derive_daemon_addr("office", config)
            expected = "unix:///home/user/.config/wingman/office/office.sock"
            assert addr == expected


class TestDeriveNetbirdRuntime:
    def test_linux_non_root_uses_state_dir(self) -> None:
        config_dir = Path("/home/user/.config/wingman/office")
        with (
            patch("wingman.platform.sys.platform", "linux"),
            patch("wingman.platform._is_root", return_value=False),
            patch("wingman.platform.getpass.getuser", return_value="alice"),
        ):
            config_path, env = derive_netbird_runtime(config_dir)

        assert config_path == config_dir / "alice" / "personal.json"
        assert env == {"NB_STATE_DIR": str(config_dir)}

    def test_linux_root_isolates_state_dir(self) -> None:
        config_dir = Path("/root/.config/wingman/office")
        with (
            patch("wingman.platform.sys.platform", "linux"),
            patch("wingman.platform._is_root", return_value=True),
        ):
            config_path, env = derive_netbird_runtime(config_dir)

        assert config_path == config_dir / "config.json"
        # Root must also isolate NB_STATE_DIR, or the daemon shares
        # /var/lib/netbird with the system install and collides over wt0.
        assert env == {"NB_STATE_DIR": str(config_dir)}

    def test_non_linux_uses_plain_config(self) -> None:
        config_dir = Path("/Users/user/.config/wingman/office")
        with patch("wingman.platform.sys.platform", "darwin"):
            config_path, env = derive_netbird_runtime(config_dir)

        assert config_path == config_dir / "config.json"
        assert env == {}


class TestDeriveInterfaceName:
    def test_linux_prefix(self) -> None:
        config = PlatformConfig(config_root=Path("/tmp"), interface_prefix="wt")
        name = derive_interface_name("office", config)
        assert name.startswith("wt")
        index = int(name[2:])
        assert 1 <= index <= 99

    def test_darwin_prefix(self) -> None:
        config = PlatformConfig(config_root=Path("/tmp"), interface_prefix="utun")
        name = derive_interface_name("office", config)
        assert name.startswith("utun")
        index = int(name[4:])
        assert 1 <= index <= 99

    def test_deterministic(self) -> None:
        config = PlatformConfig(config_root=Path("/tmp"), interface_prefix="wt")
        assert derive_interface_name("office", config) == derive_interface_name(
            "office", config
        )

    def test_different_names(self) -> None:
        config = PlatformConfig(config_root=Path("/tmp"), interface_prefix="wt")
        assert derive_interface_name("office", config) != derive_interface_name(
            "home", config
        )


class TestResolvedDnsState:
    def _run(self, tmp_path, is_active: bool, resolv_conf):
        from wingman.platform import resolved_dns_state

        with (
            patch("wingman.platform.sys.platform", "linux"),
            patch("wingman.platform.shutil.which", return_value="/usr/bin/systemctl"),
            patch(
                "wingman.platform.subprocess.run",
                return_value=MagicMock(returncode=0 if is_active else 3),
            ),
        ):
            return resolved_dns_state(resolv_conf)

    def test_none_off_linux(self, tmp_path) -> None:
        from wingman.platform import resolved_dns_state

        with patch("wingman.platform.sys.platform", "win32"):
            assert resolved_dns_state(tmp_path / "resolv.conf") is None

    def test_none_without_systemctl(self, tmp_path) -> None:
        from wingman.platform import resolved_dns_state

        with (
            patch("wingman.platform.sys.platform", "linux"),
            patch("wingman.platform.shutil.which", return_value=None),
        ):
            assert resolved_dns_state(tmp_path / "resolv.conf") is None

    def test_inactive_when_unit_not_running(self, tmp_path) -> None:
        rc = tmp_path / "resolv.conf"
        rc.write_text("nameserver 192.168.1.1\n")
        assert self._run(tmp_path, False, rc) == "inactive"

    def test_active_when_stub_symlink(self, tmp_path) -> None:
        rc = tmp_path / "resolv.conf"
        rc.symlink_to("/run/systemd/resolve/stub-resolv.conf")
        # dangling on the test host is fine — only the target path matters
        assert self._run(tmp_path, True, rc) == "active"

    def test_active_when_stub_copied(self, tmp_path) -> None:
        rc = tmp_path / "resolv.conf"
        rc.write_text("# managed by resolved\nnameserver 127.0.0.53\noptions edns0\n")
        assert self._run(tmp_path, True, rc) == "active"

    def test_unmanaged_when_networkmanager_owns_it(self, tmp_path) -> None:
        rc = tmp_path / "resolv.conf"
        rc.write_text("# Generated by NetworkManager\nnameserver 192.168.1.1\n")
        assert self._run(tmp_path, True, rc) == "unmanaged"

    def test_unmanaged_when_missing(self, tmp_path) -> None:
        assert self._run(tmp_path, True, tmp_path / "absent") == "unmanaged"
