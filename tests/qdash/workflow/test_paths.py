import importlib.util
from pathlib import Path

import pytest

# Import the leaf module without executing qdash.workflow.__init__, which eagerly
# imports Prefect/Dask and makes this pure path test depend on process discovery.
_SPEC = importlib.util.spec_from_file_location(
    "qdash_workflow_paths_for_test",
    Path(__file__).parents[3] / "src" / "qdash" / "workflow" / "paths.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
PathResolver = _MODULE.PathResolver


def test_project_scoped_calibration_paths() -> None:
    resolver = PathResolver(calib_data_base=Path("/calib"))

    assert resolver.classifier_dir("proj-1", "chip-1") == Path(
        "/calib/projects/proj-1/chips/chip-1/shared/classifier"
    )
    assert resolver.execution_data_dir("proj-1", "chip-1", "20240101-001") == Path(
        "/calib/projects/proj-1/chips/chip-1/executions/20240101/001"
    )


def test_execution_data_dir_rejects_malformed_execution_id() -> None:
    resolver = PathResolver(calib_data_base=Path("/calib"))

    with pytest.raises(ValueError, match="Invalid execution_id"):
        resolver.execution_data_dir("proj-1", "chip-1", "invalid")


def test_legacy_user_data_dir_remains_available_for_migration() -> None:
    resolver = PathResolver(calib_data_base=Path("/calib"))

    assert resolver.user_data_dir("alice") == Path("/calib/alice")
