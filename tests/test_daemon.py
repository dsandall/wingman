from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from wingman.config import ensure_instance_dir, write_pid
from wingman.daemon import is_process_alive, start_daemon, stop_daemon


class TestIsProcessAlive:
    def test_dead_process(self) -> None:
        assert is_process_alive(99999999) is False

    def test_alive_process(self) -> None:
        assert is_process_alive(os.getpid()) is True


class TestStartDaemon:
    def test_start_success(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        mock_proc = MagicMock()
        mock_proc.pid = 42

        with (
            patch("wingman.daemon.netbird.run_service", return_value=mock_proc),
            patch("wingman.daemon.is_process_alive", return_value=True),
        ):
            pid = start_daemon(
                netbird_bin="netbird",
                config_path=tmp_path / "office" / "config.json",
                daemon_addr="tcp://127.0.0.1:52200",
                config_root=tmp_path,
                name="office",
                log_file=tmp_path / "office" / "daemon.log",
            )
            assert pid == 42

    def test_start_failure(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        mock_proc = MagicMock()
        mock_proc.pid = 42

        with (
            patch("wingman.daemon.netbird.run_service", return_value=mock_proc),
            patch("wingman.daemon.is_process_alive", return_value=False),
            patch("wingman.daemon.time.sleep"),
        ):
            try:
                start_daemon(
                    netbird_bin="netbird",
                    config_path=tmp_path / "office" / "config.json",
                    daemon_addr="tcp://127.0.0.1:52200",
                    config_root=tmp_path,
                    name="office",
                    log_file=tmp_path / "office" / "daemon.log",
                )
                raise AssertionError("Should have raised RuntimeError")
            except RuntimeError as e:
                assert "office" in str(e)


class TestStopDaemon:
    def test_stop_no_pid(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        stop_daemon(tmp_path, "office")  # should not raise

    def test_stop_stale_pid(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        write_pid(tmp_path, "office", 99999999)
        with patch("wingman.daemon.is_process_alive", return_value=False):
            stop_daemon(tmp_path, "office")
        from wingman.config import read_pid

        assert read_pid(tmp_path, "office") is None
