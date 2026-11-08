"""The Copilot's source access serves text source inside fixed roots and nothing else."""

from pathlib import Path

import pytest

from qdash.api.services import source_access_service
from qdash.api.services.source_access_service import (
    QDASH_EXCLUDED_PREFIXES,
    SourceAccessError,
    SourceAccessService,
    SourceRoot,
)


@pytest.fixture
def roots(tmp_path: Path) -> tuple[SourceRoot, ...]:
    qdash = tmp_path / "src" / "qdash"
    (qdash / "workflow" / "engine").mkdir(parents=True)
    (qdash / "workflow" / "engine" / "runner.py").write_text(
        "def run():\n    raise ValueError('bad readout')\n"
    )
    (qdash / "workflow" / "user_flows" / "alice").mkdir(parents=True)
    (qdash / "workflow" / "user_flows" / "alice" / "flow.py").write_text("SECRET_FLOW = 1\n")
    (qdash / ".env").write_text("TOKEN=bad readout\n")
    (qdash / "__pycache__").mkdir()
    (qdash / "__pycache__" / "runner.py").write_text("bad readout\n")
    (qdash / "data.bin").write_text("bad readout\n")
    (qdash / "big.py").write_text("\n".join(f"line {n}" for n in range(1, 1001)))
    outside = tmp_path / "outside.py"
    outside.write_text("bad readout outside\n")
    (qdash / "escape.py").symlink_to(outside)

    qubex = tmp_path / "site-packages" / "qubex"
    qubex.mkdir(parents=True)
    (qubex / "measurement.py").write_text("class Measurement:\n    pass\n")
    return (
        SourceRoot(
            name="qdash",
            path=qdash.resolve(),
            kind="qdash",
            revision="abc123",
            revision_source="git",
            excluded_prefixes=QDASH_EXCLUDED_PREFIXES,
        ),
        SourceRoot(name="qubex", path=qubex.resolve(), kind="dependency", version="1.0"),
    )


def test_content_search_skips_hidden_cached_binary_user_flows_and_escaping_links(roots):
    service = SourceAccessService(roots)
    matches, truncated = service.search("BAD READOUT")
    assert not truncated
    assert [(m.root, m.path, m.line) for m in matches] == [
        ("qdash", "workflow/engine/runner.py", 2)
    ]
    assert service.search("SECRET_FLOW")[0] == []


def test_path_search_and_root_filter(roots):
    service = SourceAccessService(roots)
    matches, _ = service.search("measurement", mode="path")
    assert [(m.root, m.path, m.line) for m in matches] == [("qubex", "measurement.py", None)]
    assert service.search("measurement", mode="path", root_name="qdash")[0] == []
    with pytest.raises(SourceAccessError) as exc:
        service.search("x", root_name="numpy")
    assert exc.value.status == 404


def test_search_limits(roots):
    service = SourceAccessService(roots)
    matches, truncated = service.search("line", root_name="qdash", path_prefix="big.py", limit=3)
    assert [m.line for m in matches] == [1, 2, 3]
    assert truncated
    with pytest.raises(SourceAccessError):
        service.search("   ")
    with pytest.raises(SourceAccessError):
        service.search("x", path_prefix="../")


def test_read_returns_numbered_bounded_ranges(roots):
    service = SourceAccessService(roots)
    head = service.read("qdash", "big.py")
    assert (head.start_line, head.end_line, head.total_lines) == (1, 400, 1000)
    assert head.truncated
    assert head.content.splitlines()[0] == "    1  line 1"
    part = service.read("qdash", "big.py", start_line=10, end_line=12)
    assert part.content.splitlines() == ["   10  line 10", "   11  line 11", "   12  line 12"]
    assert not part.truncated


@pytest.mark.parametrize(
    ("path", "status"),
    [
        ("../outside.py", 400),
        ("/etc/passwd", 403),
        (".env", 403),
        ("data.bin", 403),
        ("workflow/user_flows/alice/flow.py", 403),
        ("escape.py", 400),
        ("missing.py", 404),
    ],
)
def test_read_refuses_paths_outside_the_served_source(roots, path, status):
    with pytest.raises(SourceAccessError) as exc:
        SourceAccessService(roots).read("qdash", path)
    assert exc.value.status == status


def test_read_maps_traceback_paths_onto_roots(roots):
    service = SourceAccessService(roots)
    worker = service.read(None, "/app/qdash/workflow/engine/runner.py", start_line=2, end_line=2)
    assert (worker.root, worker.path) == ("qdash", "workflow/engine/runner.py")
    assert "bad readout" in worker.content
    dependency = service.read(None, "/app/.venv/lib/python3.11/site-packages/qubex/measurement.py")
    assert (dependency.root, dependency.path) == ("qubex", "measurement.py")
    with pytest.raises(SourceAccessError) as exc:
        service.read(None, "/usr/lib/python3.11/json/decoder.py")
    assert exc.value.status == 404


def test_traceback_paths_through_qdash_dirs_named_after_dependencies_stay_in_qdash(roots):
    # QDash's calibration tasks live in workflow/calibtasks/qubex/, so a task
    # traceback names a "qubex" segment that is not the qubex package.
    tasks = roots[0].path / "workflow" / "calibtasks" / "qubex"
    tasks.mkdir(parents=True)
    (tasks / "base.py").write_text("class QubexTask:\n    raise RuntimeError('fit failed')\n")
    service = SourceAccessService(roots)
    task = service.read(None, "/app/qdash/workflow/calibtasks/qubex/base.py")
    assert (task.root, task.path) == ("qdash", "workflow/calibtasks/qubex/base.py")
    assert "fit failed" in task.content
    # A dependency installed under a checkout named qdash is still the dependency.
    installed = service.read(
        None, "/home/u/qdash/.venv/lib/python3.11/site-packages/qubex/measurement.py"
    )
    assert (installed.root, installed.path) == ("qubex", "measurement.py")
    # Another installed package is not mapped onto a root that happens to be in its path.
    assert service.locate("/home/u/qdash/.venv/lib/python3.11/site-packages/numpy/core.py") is None


def test_missing_dependencies_are_reported(roots, monkeypatch):
    monkeypatch.setenv("QDASH_SOURCE_DEPENDENCIES", "qubex,qubecalib")
    assert SourceAccessService(roots).missing_dependencies() == ["qubecalib"]


def test_qdash_root_prefers_configured_path_and_revision(tmp_path, monkeypatch):
    monkeypatch.setenv("QDASH_SOURCE_ROOT", str(tmp_path))
    monkeypatch.setenv("QDASH_SOURCE_REVISION", "deadbeef")
    root = source_access_service._qdash_root()
    assert root is not None
    assert (root.path, root.revision, root.revision_source) == (
        tmp_path.resolve(),
        "deadbeef",
        "QDASH_SOURCE_REVISION",
    )
    monkeypatch.delenv("QDASH_SOURCE_REVISION")
    # Not a git checkout: the revision stays unknown rather than guessed.
    unknown = source_access_service._qdash_root()
    assert unknown is not None
    assert unknown.revision is None


def test_search_cannot_read_excluded_targets_through_aliases(roots):
    root = roots[0].path
    (root / "alias.py").symlink_to(root / "workflow/user_flows/alice/flow.py")
    (root / "cached.py").symlink_to(root / "__pycache__/runner.py")
    service = SourceAccessService(roots)
    assert service.search("SECRET_FLOW")[0] == []
    assert service.search("alias.py", mode="path")[0] == []
    assert service.search("SECRET_FLOW", path_prefix="alias.py")[0] == []
    matches, _ = service.search("bad readout")
    assert [match.path for match in matches] == ["workflow/engine/runner.py"]


def test_editable_dependency_beneath_qdash_uses_its_configured_root(tmp_path):
    """Prefer the most specific configured directory over package-name segments."""
    checkout = tmp_path / "qdash"
    dependency = checkout / "vendor" / "qubex" / "qubex"
    dependency.mkdir(parents=True)
    source = dependency / "measurement.py"
    source.write_text("class Measurement: pass\n")
    service = SourceAccessService(
        (
            SourceRoot(name="qdash", path=checkout, kind="qdash"),
            SourceRoot(name="qubex", path=dependency, kind="dependency"),
        )
    )
    result = service.read(None, str(source))
    assert (result.root, result.path) == ("qubex", "measurement.py")
    assert "class Measurement" in result.content


def test_configured_traceback_paths_still_enforce_exclusions(roots):
    """An exact root match must still reject private files and escaping links."""
    service = SourceAccessService(roots)
    for relative in ("workflow/user_flows/alice/flow.py", "escape.py"):
        with pytest.raises(SourceAccessError):
            service.read(None, str(roots[0].path / relative))


def test_the_package_qualified_executor_path_reads_from_the_real_qdash_root(monkeypatch):
    # The path a user's investigation sent to the config file API, read the right way.
    monkeypatch.delenv("QDASH_SOURCE_ROOT", raising=False)
    root = source_access_service._qdash_root()
    assert root is not None
    service = SourceAccessService((root,))
    for root_name, path in (
        (None, "qdash/workflow/engine/task/executor.py"),
        ("qdash", "workflow/engine/task/executor.py"),
    ):
        source = service.read(root_name, path, start_line=1, end_line=5)
        assert (source.root, source.path) == ("qdash", "workflow/engine/task/executor.py")
        assert (source.start_line, source.end_line) == (1, 5)
        assert source.total_lines > 5
