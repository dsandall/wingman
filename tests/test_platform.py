from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from twinbird.platform import (
    PlatformConfig,
    derive_daemon_addr,
    derive_interface_name,
    derive_netbird_runtime,
    get_platform_config,
)


class TestGetPlatformConfig:
    def test_linux_defaults(self) -> None:
        with (
            patch("twinbird.platform.sys.platform", "linux"),
            patch("twinbird.platform.Path.home", return_value=Path("/home/user")),
            patch.dict("os.environ", {}, clear=True),
        ):
            config = get_platform_config()
            assert config.config_root == Path("/home/user/.config/twinbird")
            assert config.interface_prefix == "wt"

    def test_windows_defaults(self) -> None:
        with (
            patch("twinbird.platform.sys.platform", "win32"),
            patch.dict(
                "os.environ",
                {"APPDATA": "C:/Users/user/AppData/Roaming"},
                clear=True,
            ),
        ):
            config = get_platform_config()
            assert config.config_root == Path("C:/Users/user/AppData/Roaming/twinbird")
            assert config.interface_prefix == "wt"

    def test_darwin_defaults(self) -> None:
        with (
            patch("twinbird.platform.sys.platform", "darwin"),
            patch("twinbird.platform.Path.home", return_value=Path("/Users/user")),
            patch.dict("os.environ", {}, clear=True),
        ):
            config = get_platform_config()
            assert config.config_root == Path("/Users/user/.config/twinbird")
            assert config.interface_prefix == "utun"

    def test_env_override(self) -> None:
        with (
            patch("twinbird.platform.sys.platform", "linux"),
            patch.dict("os.environ", {"TWINBIRD_CONFIG_DIR": "/custom/path"}),
        ):
            config = get_platform_config()
            assert config.config_root == Path("/custom/path")


class TestDeriveDaemonAddr:
    def test_windows_tcp(self) -> None:
        config = PlatformConfig(
            config_root=Path("C:/Users/user/AppData/twinbird"),
            interface_prefix="wt",
        )
        with patch("twinbird.platform.sys.platform", "win32"):
            addr = derive_daemon_addr("office", config)
            assert addr.startswith("tcp://127.0.0.1:")
            port = int(addr.split(":")[-1])
            assert 52160 <= port <= 52959

    def test_deterministic(self) -> None:
        config = PlatformConfig(
            config_root=Path("/home/user/.config/twinbird"),
            interface_prefix="wt",
        )
        with patch("twinbird.platform.sys.platform", "win32"):
            assert derive_daemon_addr("office", config) == derive_daemon_addr(
                "office", config
            )

    def test_different_names_different_addrs(self) -> None:
        config = PlatformConfig(
            config_root=Path("/home/user/.config/twinbird"),
            interface_prefix="wt",
        )
        with patch("twinbird.platform.sys.platform", "win32"):
            assert derive_daemon_addr("office", config) != derive_daemon_addr(
                "home", config
            )

    def test_linux_root(self) -> None:
        config = PlatformConfig(
            config_root=Path("/home/user/.config/twinbird"),
            interface_prefix="wt",
        )
        with (
            patch("twinbird.platform.sys.platform", "linux"),
            patch("twinbird.platform._is_root", return_value=True),
        ):
            addr = derive_daemon_addr("office", config)
            assert addr == "unix:///var/run/twinbird-office.sock"

    def test_linux_non_root(self) -> None:
        config = PlatformConfig(
            config_root=Path("/home/user/.config/twinbird"),
            interface_prefix="wt",
        )
        with (
            patch("twinbird.platform.sys.platform", "linux"),
            patch("twinbird.platform._is_root", return_value=False),
        ):
            addr = derive_daemon_addr("office", config)
            expected = "unix:///home/user/.config/twinbird/office/office.sock"
            assert addr == expected


class TestDeriveNetbirdRuntime:
    def test_linux_non_root_uses_state_dir(self) -> None:
        config_dir = Path("/home/user/.config/twinbird/office")
        with (
            patch("twinbird.platform.sys.platform", "linux"),
            patch("twinbird.platform._is_root", return_value=False),
            patch("twinbird.platform.getpass.getuser", return_value="alice"),
        ):
            config_path, env = derive_netbird_runtime(config_dir)

        assert config_path == config_dir / "alice" / "personal.json"
        assert env == {"NB_STATE_DIR": str(config_dir)}

    def test_linux_root_isolates_state_dir(self) -> None:
        config_dir = Path("/root/.config/twinbird/office")
        with (
            patch("twinbird.platform.sys.platform", "linux"),
            patch("twinbird.platform._is_root", return_value=True),
        ):
            config_path, env = derive_netbird_runtime(config_dir)

        assert config_path == config_dir / "config.json"
        # Root must also isolate NB_STATE_DIR, or the daemon shares
        # /var/lib/netbird with the system install and collides over wt0.
        assert env == {"NB_STATE_DIR": str(config_dir)}

    def test_non_linux_uses_plain_config(self) -> None:
        config_dir = Path("/Users/user/.config/twinbird/office")
        with patch("twinbird.platform.sys.platform", "darwin"):
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
