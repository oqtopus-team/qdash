import ast
import json
from pathlib import Path

import pytest

from qdash.api.dependencies import get_task_file_service
from qdash.api.services.chip.service import _get_task_names_cached, get_task_names
from qdash.api.services.task_file_service import TaskFileService
from qdash.common.config.backend import clear_cache as clear_backend_config_cache


def test_uses_calib_tasks_path_from_environment(monkeypatch, tmp_path: Path) -> None:
    calibtasks_dir = tmp_path / "calibtasks"
    (calibtasks_dir / "fake").mkdir(parents=True)
    (calibtasks_dir / "qubex").mkdir()
    monkeypatch.setenv("CALIB_TASKS_PATH", str(calibtasks_dir))

    service = TaskFileService()

    assert service._base_path == calibtasks_dir.resolve()
    assert [backend.name for backend in service.list_backends().backends] == ["fake", "qubex"]


def test_uses_legacy_caltasks_path_from_environment(monkeypatch, tmp_path: Path) -> None:
    calibtasks_dir = tmp_path / "calibtasks"
    calibtasks_dir.mkdir()
    monkeypatch.delenv("CALIB_TASKS_PATH", raising=False)
    monkeypatch.setenv("CALTASKS_PATH", str(calibtasks_dir))

    service = TaskFileService()

    assert service._base_path == calibtasks_dir.resolve()


def test_falls_back_to_container_calibtasks_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CALIB_TASKS_PATH", raising=False)
    monkeypatch.delenv("CALTASKS_PATH", raising=False)
    calibtasks_dir = tmp_path / "calibtasks"
    calibtasks_dir.mkdir()
    monkeypatch.setattr(
        "qdash.common.config.path_resolver.CALIBTASKS_DIR",
        calibtasks_dir,
    )

    service = TaskFileService()

    assert service._base_path == calibtasks_dir


def test_ignores_nonexistent_caltasks_path_from_environment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CALIB_TASKS_PATH", str(tmp_path / "missing"))
    monkeypatch.delenv("CALTASKS_PATH", raising=False)
    calibtasks_dir = tmp_path / "calibtasks"
    calibtasks_dir.mkdir()
    monkeypatch.setattr(
        "qdash.common.config.path_resolver.CALIBTASKS_DIR",
        calibtasks_dir,
    )

    service = TaskFileService()

    assert service._base_path == calibtasks_dir


def test_falls_back_to_repo_local_calibtasks_path_when_container_path_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("CALIB_TASKS_PATH", raising=False)
    monkeypatch.delenv("CALTASKS_PATH", raising=False)
    monkeypatch.chdir(Path(__file__).parents[4])
    monkeypatch.setattr(
        "qdash.common.config.path_resolver.CALIBTASKS_DIR",
        Path("/missing/calibtasks"),
    )

    service = TaskFileService()

    assert service._base_path == (Path.cwd() / "src/qdash/workflow/calibtasks").resolve()


def test_explicit_calibtasks_base_path_takes_precedence(monkeypatch, tmp_path: Path) -> None:
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    monkeypatch.setenv("CALIB_TASKS_PATH", str(tmp_path / "from-env"))

    service = TaskFileService(calibtasks_base_path=explicit_dir)

    assert service._base_path == explicit_dir


def test_get_settings_uses_effective_default_backend_from_environment(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DEFAULT_BACKEND", "fake")
    monkeypatch.setenv("CALIB_TASKS_PATH", str(tmp_path))
    clear_backend_config_cache()

    service = TaskFileService()

    assert service.get_settings().default_backend == "fake"


def test_get_task_names_uses_effective_default_backend_and_resolved_calibtasks_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calibtasks_dir = tmp_path / "calibtasks"
    fake_dir = calibtasks_dir / "fake"
    qubex_dir = calibtasks_dir / "qubex"
    fake_dir.mkdir(parents=True)
    qubex_dir.mkdir()
    (fake_dir / "fake_task.py").write_text(
        'class FakeTask:\n    name: str = "FakeOnlyTask"\n    task_type: str = "qubit"\n',
        encoding="utf-8",
    )
    (qubex_dir / "qubex_task.py").write_text(
        'class QubexTask:\n    name: str = "QubexOnlyTask"\n    task_type: str = "qubit"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CALIB_TASKS_PATH", str(calibtasks_dir))
    monkeypatch.setenv("DEFAULT_BACKEND", "fake")
    clear_backend_config_cache()
    get_task_file_service.cache_clear()
    _get_task_names_cached.cache_clear()

    assert get_task_names() == ["FakeOnlyTask"]

    get_task_file_service.cache_clear()
    _get_task_names_cached.cache_clear()


def test_list_task_info_includes_simultaneous_qubit_spectroscopy_as_qubit() -> None:
    clear_backend_config_cache()
    service = TaskFileService()

    tasks = service.list_task_info("qubex").tasks
    task = next(t for t in tasks if t.name == "CheckSimultaneousQubitSpectroscopy")

    assert task.task_type == "qubit"
    assert task.enabled is True
    assert task.category == "CW"
    assert task.run_parameters


def test_list_task_info_uses_configured_category_and_task_order() -> None:
    clear_backend_config_cache()

    tasks = TaskFileService().list_task_info("qubex", sort_order="category").tasks
    enabled_tasks = [task for task in tasks if task.enabled]

    assert [task.category for task in enabled_tasks[:3]] == ["One Qubit"] * 3
    assert [task.name for task in enabled_tasks[:3]] == [
        "CheckChevron",
        "CheckCoarseChevron",
        "CheckFineChevron",
    ]
    assert list(dict.fromkeys(task.category for task in enabled_tasks)) == [
        "One Qubit",
        "Two Qubit",
        "CW",
        "Other",
    ]


def test_list_task_info_extracts_input_parameter_metadata() -> None:
    clear_backend_config_cache()
    service = TaskFileService()

    tasks = service.list_task_info("fake").tasks
    task = next(t for t in tasks if t.name == "CheckRabi")

    assert task.input_parameters["qubit_frequency"]["resolution"] == "default_only"


def test_list_task_info_resolves_local_and_qubex_constants() -> None:
    from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
    from qubex.measurement.measurement_defaults import DEFAULT_READOUT_DURATION

    clear_backend_config_cache()
    task = next(
        task for task in TaskFileService().list_task_info("qubex").tasks if task.name == "CheckRabi"
    )

    assert task.input_parameters["control_amplitude"]["default_value"] == 0.0125
    assert task.input_parameters["readout_length"]["default_value"] == DEFAULT_READOUT_DURATION
    assert task.run_parameters["shots"]["value"] == CALIBRATION_SHOTS
    assert task.run_parameters["interval"]["value"] == 150 * 1024

    check_t1 = next(
        task for task in TaskFileService().list_task_info("qubex").tasks if task.name == "CheckT1"
    )
    assert check_t1.run_parameters["time_range"]["value"] == [
        2.0,
        pytest.approx(5.698970004336019),
        51,
    ]


def test_list_task_info_prefers_generated_catalog(tmp_path: Path) -> None:
    backend_dir = tmp_path / "qubex"
    backend_dir.mkdir()
    (backend_dir / "ignored.py").write_text(
        'class Ignored:\n    name = "FromAst"\n', encoding="utf-8"
    )
    (tmp_path / "task_catalog.json").write_text(
        json.dumps(
            {
                "version": 1,
                "backends": {
                    "qubex": [
                        {
                            "name": "FromCatalog",
                            "class_name": "CatalogTask",
                            "task_type": "qubit",
                            "file_path": "catalog_task.py",
                            "input_parameters": {"readout_length": {"default_value": 384.0}},
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    task = TaskFileService(calibtasks_base_path=tmp_path).list_task_info("qubex").tasks[0]

    assert task.name == "FromCatalog"
    assert task.input_parameters["readout_length"]["default_value"] == 384.0


def test_list_task_info_includes_database_input_parameter_dependencies() -> None:
    clear_backend_config_cache()
    service = TaskFileService()

    tasks = service.list_task_info("qubex").tasks
    task = next(t for t in tasks if t.name == "CheckT2EchoAverage")

    assert set(task.input_parameters) == {
        "qubit_frequency",
        "hpi_amplitude",
        "hpi_length",
        "readout_amplitude",
        "readout_frequency",
        "readout_length",
    }
    assert task.input_parameters["qubit_frequency"] == {
        "resolution": "database_required",
        "user_override": "allowed",
        "default_value": None,
    }
    assert task.input_parameters["readout_length"]["unit"] == "ns"


def test_extract_parameter_metadata_understands_named_spec_constructors() -> None:
    node = ast.parse(
        """{
            "frequency": InputParameterSpec.required_database(unit="GHz"),
            "amplitude": InputParameterSpec.database_or_default(
                default=0.1,
                user_override="forbidden",
                greater_than=0.0,
            ),
        }""",
        mode="eval",
    ).body

    assert TaskFileService._extract_parameter_metadata(node) == {
        "frequency": {
            "resolution": "database_required",
            "user_override": "allowed",
            "default_value": None,
            "unit": "GHz",
        },
        "amplitude": {
            "resolution": "database_or_default",
            "user_override": "forbidden",
            "default_value": 0.1,
            "greater_than": 0.0,
        },
    }
