"""QDash.qubex: the calibration note and the safe export of the Qubex configuration tree."""

from __future__ import annotations

import io
import json
import stat
import zipfile
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from test_sdk_session import Server

from qdash.sdk import (
    QDashApiError,
    QDashAuthError,
    QDashNotFoundError,
    QDashTransportError,
    UnsafeArchiveError,
)
from qdash.sdk.types import CalibrationNoteResponse

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    # The generated client waits between read attempts; the tests do not need to.
    monkeypatch.setattr("qdash.sdk._generated.core.http_client.time.sleep", lambda _: None)


NOTE: dict[str, Any] = {"cr_params": {"Q00-Q01": {"duration": 100}}, "label": "量子"}
NOTE_ROUTE = ("GET", "/calibrations/note")
ZIP_ROUTE = ("GET", "/files/zip")


def make_zip(*members: tuple[str, bytes | None] | zipfile.ZipInfo, data: bytes = b"") -> bytes:
    """A ZIP archive; a None content makes a directory entry."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for member in members:
            if isinstance(member, zipfile.ZipInfo):
                archive.writestr(member, data)
                continue
            name, content = member
            if content is None:
                archive.writestr(zipfile.ZipInfo(name if name.endswith("/") else name + "/"), b"")
            else:
                archive.writestr(name, content)
    return buffer.getvalue()


# Shaped as shutil.make_archive packs the configured root: relative paths, directory entries.
CONFIG_ZIP = make_zip(
    ("64Qv3/", None),
    ("64Qv3/config/", None),
    ("64Qv3/config/chip.yaml", b"chip: 64Qv3\n"),
    ("64Qv3/params/params.yaml", b"a: 1\n"),
    ("calib_note.json", b'{"stale": true}'),
    (".git/HEAD", b"ref: refs/heads/main\n"),
)


def note_response(note: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "username": "admin",
            "execution_id": "e1",
            "task_id": "t1",
            "note": NOTE if note is None else note,
            "timestamp": "2026-11-24T00:00:00Z",
        },
    )


def zip_response(content: bytes = CONFIG_ZIP, **headers: str) -> httpx.Response:
    return httpx.Response(
        200, content=content, headers={"content-type": "application/zip", **headers}
    )


def server(zip_: httpx.Response | None = None, note: httpx.Response | None = None) -> Server:
    return Server({NOTE_ROUTE: [note or note_response()], ZIP_ROUTE: [zip_ or zip_response()]})


def tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def snapshot(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


def test_calibration_note_reads_the_latest_note_with_retries() -> None:
    fake = Server({NOTE_ROUTE: [httpx.Response(503), note_response()]})
    with fake.session(project_id="project-b") as qdash:
        note = qdash.qubex.calibration_note()

    assert isinstance(note, CalibrationNoteResponse)
    assert note.note == NOTE
    assert fake.paths() == [NOTE_ROUTE, NOTE_ROUTE]
    assert all(request.headers["X-Project-Id"] == "project-b" for request in fake.requests)


def test_calibration_note_missing_raises_not_found() -> None:
    fake = Server({NOTE_ROUTE: [httpx.Response(404, json={"detail": "not found"})]})
    with fake.session() as qdash, pytest.raises(QDashNotFoundError):
        qdash.qubex.calibration_note()


def test_download_config_unpacks_the_tree_and_writes_the_latest_note(tmp_path: Path) -> None:
    fake = server()
    destination = tmp_path / "qubex-config"
    with fake.session(project_id="project-b") as qdash:
        result = qdash.qubex.download_config(destination)

    assert result == destination
    files = tree(destination)
    assert files["64Qv3/config/chip.yaml"] == b"chip: 64Qv3\n"
    assert files["64Qv3/params/params.yaml"] == b"a: 1\n"
    assert files[".git/HEAD"] == b"ref: refs/heads/main\n"
    # The API's note wins over the archive's calib_note.json.
    assert json.loads(files["calib_note.json"]) == NOTE
    assert "量子" in files["calib_note.json"].decode("utf-8")
    assert set(files) == {
        "64Qv3/config/chip.yaml",
        "64Qv3/params/params.yaml",
        "calib_note.json",
        ".git/HEAD",
    }
    # Nothing left behind next to the destination.
    assert snapshot(tmp_path)[0] == "qubex-config"
    assert [path.name for path in tmp_path.iterdir()] == ["qubex-config"]
    assert sorted(fake.paths()) == sorted([NOTE_ROUTE, ZIP_ROUTE])
    zip_request = next(r for r in fake.requests if r.url.path == "/files/zip")
    assert zip_request.url.params["path"] == "."
    assert zip_request.headers["Authorization"] == "Bearer api-token"
    assert all(request.headers["X-Project-Id"] == "project-b" for request in fake.requests)
    mode = stat.S_IMODE((destination / "calib_note.json").stat().st_mode)
    assert mode & 0o044  # default permissions, not a private temporary file's 0600


def test_download_config_without_the_note_keeps_the_archive_file(tmp_path: Path) -> None:
    fake = server()
    with fake.session() as qdash:
        qdash.qubex.download_config(tmp_path / "qubex-config", include_calibration_note=False)

    assert (tmp_path / "qubex-config" / "calib_note.json").read_bytes() == b'{"stale": true}'
    assert fake.paths() == [ZIP_ROUTE]


def test_download_config_into_an_existing_directory_keeps_other_files(tmp_path: Path) -> None:
    destination = tmp_path / "qubex-config"
    destination.mkdir()
    (destination / "mine.txt").write_text("keep")
    with server().session() as qdash:
        qdash.qubex.download_config(destination)

    assert (destination / "mine.txt").read_text() == "keep"
    assert (destination / "64Qv3" / "config" / "chip.yaml").exists()
    assert not list(destination.rglob("*.partial"))


def test_download_config_refuses_existing_files_unless_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "qubex-config"
    (destination / "64Qv3" / "config").mkdir(parents=True)
    (destination / "64Qv3" / "config" / "chip.yaml").write_text("old")
    (destination / "calib_note.json").write_text("old note")
    (destination / "mine.txt").write_text("keep")
    before = snapshot(destination)

    with server().session() as qdash, pytest.raises(FileExistsError, match="overwrite=True"):
        qdash.qubex.download_config(destination)
    assert snapshot(destination) == before
    assert (destination / "64Qv3" / "config" / "chip.yaml").read_text() == "old"

    with server().session() as qdash:
        qdash.qubex.download_config(destination, overwrite=True)
    assert (destination / "64Qv3" / "config" / "chip.yaml").read_text() == "chip: 64Qv3\n"
    assert json.loads((destination / "calib_note.json").read_text()) == NOTE
    assert (destination / "mine.txt").read_text() == "keep"


def test_download_config_refuses_the_note_file_alone_unless_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "qubex-config"
    destination.mkdir()
    (destination / "calib_note.json").write_text("old note")
    fake = server(zip_response(make_zip(("a.yaml", b"a"))))
    with fake.session() as qdash, pytest.raises(FileExistsError):
        qdash.qubex.download_config(destination)
    assert snapshot(destination) == ["calib_note.json"]


@pytest.mark.parametrize(
    ("zip_", "note", "error"),
    [
        (None, httpx.Response(404, json={"detail": "none"}), QDashNotFoundError),
        (None, httpx.Response(401, json={"detail": "no"}), QDashAuthError),
        (httpx.Response(404, json={"detail": "Path not found"}), None, QDashNotFoundError),
        (httpx.Response(500, json={"detail": "boom"}), None, QDashApiError),
        (
            httpx.Response(200, text="<html>login</html>", headers={"content-type": "text/html"}),
            None,
            QDashTransportError,
        ),
        (zip_response(b"PK\x03\x04 not really a zip"), None, QDashTransportError),
        (zip_response(CONFIG_ZIP[:-30]), None, QDashTransportError),
    ],
)
def test_a_failed_or_malformed_download_writes_nothing(
    tmp_path: Path,
    zip_: httpx.Response | None,
    note: httpx.Response | None,
    error: type[Exception],
) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "mine.txt").write_text("keep")
    for destination in (tmp_path / "qubex-config", existing):
        with server(zip_, note).session() as qdash, pytest.raises(error):
            qdash.qubex.download_config(destination)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["existing"]
    assert snapshot(existing) == ["mine.txt"]


def corrupt_zip() -> bytes:
    """An archive whose stored data no longer matches its CRC."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("a.yaml", b"original")
    return buffer.getvalue().replace(b"original", b"tampered", 1)


def symlink_member() -> zipfile.ZipInfo:
    info = zipfile.ZipInfo("link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info


def fifo_member() -> zipfile.ZipInfo:
    info = zipfile.ZipInfo("pipe")
    info.external_attr = (stat.S_IFIFO | 0o644) << 16
    return info


@pytest.mark.parametrize(
    "archive",
    [
        make_zip(("ok.yaml", b"ok"), ("../escape.yaml", b"x")),
        make_zip(("ok.yaml", b"ok"), ("a/../../escape.yaml", b"x")),
        make_zip(("/etc/escape.yaml", b"x")),
        make_zip(("C:/escape.yaml", b"x")),
        make_zip(("a\\..\\escape.yaml", b"x")),
        make_zip(("ok.yaml", b"ok"), symlink_member()),
        make_zip(fifo_member()),
        make_zip(("a.yaml", b"1"), ("./a.yaml", b"2")),
        make_zip(("a", b"file"), ("a/b.yaml", b"x")),
        make_zip(("a", b"file"), ("a/", None)),
        make_zip(("calib_note.json/", None)),
        corrupt_zip(),
    ],
)
def test_an_unsafe_archive_writes_nothing(tmp_path: Path, archive: bytes) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    for destination in (tmp_path / "qubex-config", existing):
        with server(zip_response(archive)).session() as qdash, pytest.raises(UnsafeArchiveError):
            qdash.qubex.download_config(destination)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["existing"]
    assert snapshot(existing) == []


def test_existing_symlinks_in_the_destination_are_not_written_through(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "qubex-config"
    destination.mkdir()
    (destination / "64Qv3").symlink_to(outside, target_is_directory=True)
    with server().session() as qdash, pytest.raises(FileExistsError, match="symbolic link"):
        qdash.qubex.download_config(destination, overwrite=True)
    assert list(outside.iterdir()) == []

    (destination / "64Qv3").unlink()
    (destination / "calib_note.json").symlink_to(outside / "note.json")
    with server().session() as qdash, pytest.raises(FileExistsError, match="symbolic link"):
        qdash.qubex.download_config(destination, overwrite=True)
    assert list(outside.iterdir()) == []
    assert snapshot(destination) == ["calib_note.json"]


def test_a_directory_where_the_archive_has_a_file_is_refused(tmp_path: Path) -> None:
    destination = tmp_path / "qubex-config"
    (destination / "calib_note.json").mkdir(parents=True)
    with server().session() as qdash, pytest.raises(IsADirectoryError):
        qdash.qubex.download_config(destination, overwrite=True)
    assert snapshot(destination) == ["calib_note.json"]


def test_destination_checks_happen_before_any_request(tmp_path: Path) -> None:
    fake = server()
    (tmp_path / "file").write_text("x")
    with fake.session() as qdash:
        with pytest.raises(NotADirectoryError):
            qdash.qubex.download_config(tmp_path / "file")
        with pytest.raises(FileNotFoundError):
            qdash.qubex.download_config(tmp_path / "missing" / "qubex-config")
    assert fake.requests == []
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("overwrite", [False, True])
@pytest.mark.parametrize(
    "members",
    [
        [("A.yaml", b"first"), ("a.yaml", b"second")],
        [("Config/a.yaml", b"first"), ("config/b.yaml", b"second")],
        [("Config/", None), ("config/a.yaml", b"second")],
        [("A", b"first"), ("a/b.yaml", b"second")],
        [("CALIB_NOTE.JSON", b"stale")],
        [("CALIB_NOTE.JSON/a.yaml", b"stale")],
    ],
)
def test_case_aliases_are_rejected_before_any_writes(
    tmp_path: Path,
    existing: bool,
    overwrite: bool,
    members: list[tuple[str, bytes | None]],
) -> None:
    destination = tmp_path / "qubex-config"
    if existing:
        destination.mkdir()
        (destination / "keep.yaml").write_bytes(b"keep")
    before_paths = snapshot(tmp_path)
    before_files = tree(tmp_path)
    fake = server(zip_response(make_zip(*members)))
    with fake.session() as qdash, pytest.raises(UnsafeArchiveError, match="differ only in case"):
        qdash.qubex.download_config(destination, overwrite=overwrite)
    assert snapshot(tmp_path) == before_paths
    assert tree(tmp_path) == before_files


def test_note_casing_is_preserved_when_no_note_is_merged(tmp_path: Path) -> None:
    fake = server(zip_response(make_zip(("CALIB_NOTE.JSON", b"archive note"))))
    destination = tmp_path / "qubex-config"
    with fake.session() as qdash:
        qdash.qubex.download_config(destination, include_calibration_note=False)
    assert tree(destination) == {"CALIB_NOTE.JSON": b"archive note"}
