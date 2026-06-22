from __future__ import annotations

from pathlib import Path

from wingman.config import (
    InstanceMetadata,
    ensure_instance_dir,
    instance_dir,
    list_instances,
    read_metadata,
    read_pid,
    remove_pid,
    write_metadata,
    write_pid,
)


class TestInstanceDir:
    def test_returns_correct_path(self, tmp_path: Path) -> None:
        assert instance_dir(tmp_path, "office") == tmp_path / "office"

    def test_ensure_creates_dir(self, tmp_path: Path) -> None:
        path = ensure_instance_dir(tmp_path, "office")
        assert path.exists()
        assert path.is_dir()
        assert path == tmp_path / "office"

    def test_ensure_idempotent(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        path = ensure_instance_dir(tmp_path, "office")
        assert path.exists()


class TestMetadata:
    def _sample_metadata(self) -> InstanceMetadata:
        return InstanceMetadata(
            name="office",
            management_url="https://mgmt.example.com",
            daemon_addr="tcp://127.0.0.1:52200",
            interface_name="wt7",
            pid=12345,
            created_at="2026-03-31T18:30:00+00:00",
        )

    def test_write_and_read(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        metadata = self._sample_metadata()
        write_metadata(tmp_path, metadata)
        loaded = read_metadata(tmp_path, "office")
        assert loaded is not None
        assert loaded.name == "office"
        assert loaded.management_url == "https://mgmt.example.com"
        assert loaded.daemon_addr == "tcp://127.0.0.1:52200"
        assert loaded.interface_name == "wt7"
        assert loaded.pid == 12345

    def test_read_not_found(self, tmp_path: Path) -> None:
        assert read_metadata(tmp_path, "nonexistent") is None

    def test_backward_compat_no_service_registered(self, tmp_path: Path) -> None:
        """Existing instance.json without service_registered loads with False."""
        ensure_instance_dir(tmp_path, "old")
        path = tmp_path / "old" / "instance.json"
        import json

        path.write_text(
            json.dumps(
                {
                    "name": "old",
                    "management_url": "https://mgmt.example.com",
                    "daemon_addr": "tcp://127.0.0.1:52200",
                    "interface_name": "wt7",
                    "pid": 123,
                    "created_at": "2026-03-31T00:00:00+00:00",
                }
            )
        )
        loaded = read_metadata(tmp_path, "old")
        assert loaded is not None
        assert loaded.service_registered is False

    def test_overwrite(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        meta1 = self._sample_metadata()
        write_metadata(tmp_path, meta1)
        meta2 = InstanceMetadata(
            name="office",
            management_url="https://other.example.com",
            daemon_addr="tcp://127.0.0.1:52300",
            interface_name="wt8",
            pid=99999,
            created_at="2026-04-01T00:00:00+00:00",
        )
        write_metadata(tmp_path, meta2)
        loaded = read_metadata(tmp_path, "office")
        assert loaded is not None
        assert loaded.pid == 99999


class TestListInstances:
    def test_empty(self, tmp_path: Path) -> None:
        assert list_instances(tmp_path) == []

    def test_nonexistent_root(self) -> None:
        assert list_instances(Path("/nonexistent/path")) == []

    def test_finds_instances(self, tmp_path: Path) -> None:
        for name in ["office", "home"]:
            ensure_instance_dir(tmp_path, name)
            meta = InstanceMetadata(name, "url", "addr", "wt1", 1, "t")
            write_metadata(tmp_path, meta)
        instances = list_instances(tmp_path)
        assert sorted(instances) == ["home", "office"]

    def test_ignores_dirs_without_metadata(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        (tmp_path / "stray_dir").mkdir()
        meta = InstanceMetadata("office", "url", "addr", "wt1", 1, "t")
        write_metadata(tmp_path, meta)
        assert list_instances(tmp_path) == ["office"]


class TestPidFile:
    def test_write_and_read(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        write_pid(tmp_path, "office", 12345)
        assert read_pid(tmp_path, "office") == 12345

    def test_read_not_found(self, tmp_path: Path) -> None:
        assert read_pid(tmp_path, "office") is None

    def test_remove(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        write_pid(tmp_path, "office", 12345)
        remove_pid(tmp_path, "office")
        assert read_pid(tmp_path, "office") is None

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        remove_pid(tmp_path, "office")  # should not raise

    def test_read_corrupted(self, tmp_path: Path) -> None:
        ensure_instance_dir(tmp_path, "office")
        pid_path = tmp_path / "office" / "daemon.pid"
        pid_path.write_text("not_a_number")
        assert read_pid(tmp_path, "office") is None
