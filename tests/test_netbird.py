from __future__ import annotations

from unittest.mock import patch

from wingman.netbird import find_netbird_bin


class TestFindNetbirdBin:
    def test_found_on_path(self) -> None:
        with (
            patch("shutil.which", return_value="/usr/bin/netbird"),
            patch.dict("os.environ", {}, clear=True),
        ):
            assert find_netbird_bin() == "netbird"

    def test_not_found(self) -> None:
        with (
            patch("shutil.which", return_value=None),
            patch.dict("os.environ", {}, clear=True),
        ):
            try:
                find_netbird_bin()
                raise AssertionError("Should have raised FileNotFoundError")
            except FileNotFoundError as e:
                assert "WINGMAN_NETBIRD_BIN" in str(e)

    def test_env_override(self) -> None:
        with (
            patch("shutil.which", return_value="/custom/netbird"),
            patch.dict("os.environ", {"WINGMAN_NETBIRD_BIN": "/custom/netbird"}),
        ):
            assert find_netbird_bin() == "/custom/netbird"

    def test_env_override_not_found(self) -> None:
        with (
            patch("shutil.which", return_value=None),
            patch.dict("os.environ", {"WINGMAN_NETBIRD_BIN": "/bad/path"}),
        ):
            try:
                find_netbird_bin()
                raise AssertionError("Should have raised FileNotFoundError")
            except FileNotFoundError as e:
                assert "WINGMAN_NETBIRD_BIN" in str(e)
