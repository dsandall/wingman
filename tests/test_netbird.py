from __future__ import annotations

from unittest.mock import MagicMock, patch

from wingman.netbird import find_netbird_bin, has_net_admin_capability, run_up


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


class TestRunUp:
    def test_passes_profile_and_state_env(self) -> None:
        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            run_up(
                "netbird",
                "unix:///tmp/work.sock",
                "https://mgmt.example.com",
                interface_name="wt30",
                profile="personal",
                env={"NB_STATE_DIR": "/state/work"},
            )

        cmd = mock_run.call_args.args[0]
        assert "--profile" in cmd
        assert cmd[cmd.index("--profile") + 1] == "personal"
        passed_env = mock_run.call_args.kwargs["env"]
        assert passed_env["NB_STATE_DIR"] == "/state/work"
        # No setup key => interactive flow that streams output (not captured)
        assert "capture_output" not in mock_run.call_args.kwargs

    def test_omits_profile_when_none(self) -> None:
        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            run_up(
                "netbird",
                "unix:///tmp/work.sock",
                "https://mgmt.example.com",
                setup_key="KEY123",
            )

        cmd = mock_run.call_args.args[0]
        assert "--profile" not in cmd
        assert mock_run.call_args.kwargs["env"] is None


class TestHasNetAdminCapability:
    def test_present(self) -> None:
        with (
            patch("shutil.which", side_effect=lambda c: f"/usr/bin/{c}"),
            patch(
                "subprocess.run",
                return_value=MagicMock(
                    returncode=0,
                    stdout="/usr/bin/netbird cap_net_admin,cap_net_raw=eip",
                ),
            ),
        ):
            assert has_net_admin_capability("netbird") is True

    def test_absent(self) -> None:
        with (
            patch("shutil.which", side_effect=lambda c: f"/usr/bin/{c}"),
            patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="")),
        ):
            assert has_net_admin_capability("netbird") is False

    def test_no_getcap_is_undeterminable(self) -> None:
        with patch("shutil.which", return_value=None):
            assert has_net_admin_capability("netbird") is None
