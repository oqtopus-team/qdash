import ast
import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from qdash.api.dependencies import get_task_file_service
from qdash.api.services.chip.service import _get_task_names_cached, get_task_names
from qdash.api.services.task_file_service import (
    RABI_NORMALIZATION_INPUT_UNITS,
    TaskFileService,
)
from qdash.common.config.backend import clear_cache as clear_backend_config_cache
from tests.qdash.api._fs_swaps import swap_after_listing, swap_dir_for_link


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


def test_list_task_info_uses_configured_category_and_task_order() -> None:
    clear_backend_config_cache()

    tasks = TaskFileService().list_task_info("qubex", sort_order="category").tasks
    enabled_tasks = [task for task in tasks if task.enabled]

    assert [task.category for task in enabled_tasks[:3]] == ["One Qubit"] * 3
    assert [task.name for task in enabled_tasks[:5]] == [
        "CheckAdaptiveChevron",
        "CheckChevron",
        "CheckOptimalReadoutAmplitude",
        "CheckOptimalReadoutFrequency",
        "CheckRabi",
    ]
    assert list(dict.fromkeys(task.category for task in enabled_tasks)) == [
        "One Qubit",
        "Two Qubit",
        "CW",
        "Other",
    ]


def test_ef_chevron_is_enabled_with_calibration_and_sweep_metadata() -> None:
    clear_backend_config_cache()
    tasks = TaskFileService().list_task_info("qubex", enabled_only=True).tasks
    task = next(task for task in tasks if task.name == "CheckAdaptiveEFChevron")

    assert task.enabled
    assert task.category == "One Qubit"
    assert "qubit_frequency" not in task.input_parameters
    assert task.input_parameters["control_frequency"]["resolution"] == "database_required"
    assert task.input_parameters["control_frequency"]["fallback_parameter_names"] == [
        "qubit_frequency"
    ]
    assert not any(name.startswith("drag_pi_") for name in task.input_parameters)
    assert task.input_parameters["hpi_amplitude"]["resolution"] == "database_required"
    assert task.input_parameters["hpi_duration"]["resolution"] == "database_required"
    assert "anharmonicity" not in task.input_parameters
    assert task.input_parameters["control_amplitude"]["resolution"] == "database_required"
    assert task.input_parameters["control_amplitude"]["description"] == (
        "Calibrated GE amplitude used to derive the initial EF drive amplitude"
    )
    assert "ef_control_amplitude" not in task.input_parameters
    assert task.run_parameters["detuning_range"]["value"] == [-0.05, 0.05, 41]
    assert task.run_parameters["shots"]["value"] == 256


def test_cpmg_noise_spectroscopy_is_enabled_in_one_qubit_group() -> None:
    clear_backend_config_cache()
    task = next(
        task
        for task in TaskFileService().list_task_info("qubex", enabled_only=True).tasks
        if task.name == "CheckCPMGNoiseSpectroscopy"
    )

    assert task.enabled
    assert task.category == "One Qubit"
    assert task.task_type == "qubit"


def test_fh_chevron_is_enabled_with_transition_and_pulse_dependencies() -> None:
    clear_backend_config_cache()
    all_task_names = {task.name for task in TaskFileService().list_task_info("qubex").tasks}
    tasks = (
        TaskFileService().list_task_info("qubex", sort_order="category", enabled_only=True).tasks
    )
    task = next(task for task in tasks if task.name == "CheckAdaptiveFHChevron")
    task_names = [task.name for task in tasks]

    assert task.enabled
    assert task.category == "One Qubit"
    assert "CheckEFChevron" not in all_task_names
    assert "CheckFHChevron" not in all_task_names
    assert task_names.index("CheckAdaptiveFHChevron") > task_names.index("CreateEFPIPulse")
    assert task.input_parameters["control_frequency_ef"]["fallback_parameter_names"] == [
        "ef_frequency"
    ]
    assert task.input_parameters["control_amplitude"]["description"] == (
        "Calibrated GE amplitude used to derive the initial FH drive amplitude"
    )
    assert task.input_parameters["ef_pi_amplitude"]["resolution"] == "database_required"
    assert task.input_parameters["ef_pi_duration"]["resolution"] == "database_required"
    assert task.run_parameters["detuning_range"]["value"] == [-0.05, 0.05, 41]
    assert task.run_parameters["shots"]["value"] == 256


def test_ef_configure_is_enabled_with_mode_metadata() -> None:
    clear_backend_config_cache()
    tasks = TaskFileService().list_task_info("qubex", enabled_only=True).tasks
    task = next(task for task in tasks if task.name == "ConfigureEF")

    assert task.enabled
    assert task.category == "Other"
    assert task.task_type == "qubit"
    assert task.run_parameters["configuration_mode"]["value"] == "ge-ef-cr"
    configure = next(task for task in tasks if task.name == "Configure")
    assert configure.run_parameters["configuration_mode"]["value"] == "ge-cr-cr"


def test_jazz_task_is_enabled_in_two_qubit_group() -> None:
    from qdash.common.config.backend import is_task_available

    clear_backend_config_cache()
    task = next(
        task
        for task in TaskFileService().list_task_info("qubex", enabled_only=True).tasks
        if task.name == "CheckJAZZ"
    )

    assert task.enabled
    assert task.category == "Two Qubit"
    assert task.task_type == "coupling"
    assert is_task_available("CheckJAZZ", "qubex")


def test_coupling_strength_exposes_optional_database_anharmonicities() -> None:
    clear_backend_config_cache()
    task = next(
        task
        for task in TaskFileService().list_task_info("qubex", enabled_only=True).tasks
        if task.name == "CheckCouplingStrength"
    )

    assert task.category == "Two Qubit"
    for name in ("control_qubit_anharmonicity", "target_qubit_anharmonicity"):
        parameter = task.input_parameters[name]
        assert parameter["resolution"] == "database_optional"
        assert parameter["user_override"] == "forbidden"
        assert parameter["default_value"] is None
        assert parameter["parameter_name"] == "qubit_anharmonicity"
        assert parameter["parameter_aliases"] == ["anharmonicity"]


def test_list_task_info_extracts_input_parameter_metadata() -> None:
    clear_backend_config_cache()
    service = TaskFileService()

    tasks = service.list_task_info("qubex").tasks
    task = next(t for t in tasks if t.name == "CheckRabi")

    parameter = task.input_parameters["control_frequency"]
    assert parameter["resolution"] == "database_required"
    assert parameter["fallback_parameter_names"] == ["qubit_frequency"]


def test_fake_backend_publishes_the_qubex_task_declarations() -> None:
    """A qubex task routed to the fake backend keeps its qubex declaration in the catalog."""
    clear_backend_config_cache()
    service = TaskFileService()

    fake = {t.name: t for t in service.list_task_info("fake").tasks}
    qubex = {t.name: t for t in service.list_task_info("qubex").tasks}

    assert fake["CheckRabi"].input_parameters == qubex["CheckRabi"].input_parameters
    assert fake["CheckRabi"].run_parameters == qubex["CheckRabi"].run_parameters
    assert fake["FakeBringUp"].input_parameters == {}
    assert "FakeBringUp" not in qubex


def test_coarse_readout_task_is_enabled_with_resolvable_input_metadata() -> None:
    clear_backend_config_cache()
    task = next(
        task
        for task in TaskFileService().list_task_info("qubex", enabled_only=True).tasks
        if task.name == "CheckCoarseReadoutParams"
    )

    assert task.enabled
    assert set(task.input_parameters) == {
        "control_frequency",
        "control_amplitude",
        "readout_frequency",
        "readout_amplitude",
    }
    assert task.run_parameters["readout_duration"]["value"] == 1024
    assert task.run_parameters["readout_duration"]["unit"] == "ns"


def test_list_task_info_resolves_local_and_qubex_constants() -> None:
    from qubex.experiment.experiment_constants import CALIBRATION_SHOTS

    clear_backend_config_cache()
    task = next(
        task for task in TaskFileService().list_task_info("qubex").tasks if task.name == "CheckRabi"
    )

    assert task.input_parameters["control_amplitude"]["default_value"] == 0.0125
    assert task.run_parameters["readout_duration"]["value"] == 1024
    assert task.run_parameters["shots"]["value"] == CALIBRATION_SHOTS
    assert task.run_parameters["interval"]["value"] == 150 * 1024

    check_t1 = next(
        task for task in TaskFileService().list_task_info("qubex").tasks if task.name == "CheckT1"
    )
    assert check_t1.input_parameters["rabi_amplitude"] == {
        "resolution": "database_required",
        "user_override": "allowed",
        "default_value": None,
        "parameter_name": "rabi_amplitude",
        "qid_role": "self",
        "unit": "a.u.",
        "ui_group": "Rabi normalization",
        "ui_group_collapsed": True,
    }
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
                            "input_parameters": {"readout_duration": {"default_value": 384.0}},
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    task = TaskFileService(calibtasks_base_path=tmp_path).list_task_info("qubex").tasks[0]

    assert task.name == "FromCatalog"
    assert task.input_parameters["readout_duration"]["default_value"] == 384.0


def test_list_task_info_includes_database_input_parameter_dependencies() -> None:
    clear_backend_config_cache()
    service = TaskFileService()

    tasks = service.list_task_info("qubex").tasks
    task = next(t for t in tasks if t.name == "CheckT2EchoAverage")

    assert set(task.input_parameters) == {
        "control_frequency",
        "hpi_amplitude",
        "hpi_duration",
        "pi_amplitude",
        "pi_duration",
        "readout_amplitude",
        "readout_frequency",
    } | set(RABI_NORMALIZATION_INPUT_UNITS)
    assert task.input_parameters["control_frequency"] == {
        "resolution": "database_required",
        "user_override": "allowed",
        "default_value": None,
        "fallback_parameter_names": ["qubit_frequency"],
    }
    assert task.input_parameters["readout_frequency"]["fallback_parameter_names"] == [
        "resonator_frequency"
    ]
    assert task.input_parameters["pi_duration"]["parameter_aliases"] == ["pi_length"]
    assert task.run_parameters["readout_duration"]["unit"] == "ns"
    assert task.run_parameters["readout_duration"]["value"] == 1024


def test_list_task_info_extracts_output_parameter_names() -> None:
    clear_backend_config_cache()
    service = TaskFileService()

    tasks = {t.name: t for t in service.list_task_info("qubex").tasks}

    assert "rabi_amplitude" in tasks["CheckRabi"].output_parameters
    assert tasks["CreateHPIPulse"].output_parameters[:1] == ["hpi_amplitude"]


def test_cross_resonance_catalog_groups_control_and_target_rabi_inputs() -> None:
    task = next(
        task
        for task in TaskFileService().list_task_info("qubex").tasks
        if task.name == "CheckCrossResonance"
    )
    rabi_input_names = {
        f"{prefix}{name}"
        for prefix in ("control_", "target_")
        for name in RABI_NORMALIZATION_INPUT_UNITS
    }

    assert rabi_input_names <= set(task.input_parameters)
    assert {task.input_parameters[name]["ui_group"] for name in rabi_input_names} == {
        "Rabi normalization"
    }
    assert all(
        task.input_parameters[name]["ui_group_collapsed"] is True for name in rabi_input_names
    )


def test_extract_parameter_metadata_understands_named_spec_constructors() -> None:
    node = ast.parse(
        """{
            "frequency": InputParameterSpec.required_database(unit="GHz"),
            "amplitude": InputParameterSpec.database_or_default(
                default=0.1,
                user_override="forbidden",
                greater_than=0.0,
            ),
            "coarse_amplitude": InputParameterSpec.database_or_default(
                default=0.0625,
                greater_than_or_equal=0.0001,
                less_than_or_equal=1.0,
            ),
            "anharmonicity": InputParameterSpec.database_optional(
                unit="GHz",
                user_override="forbidden",
                less_than=0,
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
        "coarse_amplitude": {
            "resolution": "database_or_default",
            "user_override": "allowed",
            "default_value": 0.0625,
            "greater_than_or_equal": 0.0001,
            "less_than_or_equal": 1.0,
        },
        "anharmonicity": {
            "resolution": "database_optional",
            "user_override": "forbidden",
            "default_value": None,
            "unit": "GHz",
            "less_than": 0,
        },
    }


def test_extract_parameter_metadata_expands_rabi_normalization_inputs() -> None:
    node = ast.parse(
        """{
            **required_rabi_normalization_inputs(),
            **required_rabi_normalization_inputs(prefix="control_", qid_role="control"),
        }""",
        mode="eval",
    ).body

    parameters = TaskFileService._extract_parameter_metadata(node)

    assert set(parameters) == set(RABI_NORMALIZATION_INPUT_UNITS) | {
        f"control_{name}" for name in RABI_NORMALIZATION_INPUT_UNITS
    }
    assert parameters["rabi_amplitude"] == {
        "resolution": "database_required",
        "user_override": "allowed",
        "default_value": None,
        "parameter_name": "rabi_amplitude",
        "qid_role": "self",
        "unit": "a.u.",
        "ui_group": "Rabi normalization",
        "ui_group_collapsed": True,
    }
    assert parameters["control_rabi_angle"] == {
        "resolution": "database_required",
        "user_override": "allowed",
        "default_value": None,
        "parameter_name": "rabi_angle",
        "qid_role": "control",
        "unit": "rad",
        "ui_group": "Rabi normalization",
        "ui_group_collapsed": True,
    }


DOCUMENTED_TASK_SOURCE = '''
from typing import ClassVar

from qdash.datamodel.task import TaskDocumentation


class DocumentedTask:
    """Legacy docstring that documentation replaces."""

    name: str = "DocumentedTask"
    task_type: str = "qubit"
    documentation: ClassVar[TaskDocumentation] = TaskDocumentation(
        description="Measures something specific.",
        when_to_use="Run it after the qubit frequency is known.",
        prerequisites=("qubit_frequency is stored.", "A calibrated readout."),
    )


class LegacyTask:
    """Docstring-only task description."""

    name = "LegacyTask"
    task_type = "qubit"
'''


def _write_backend(tmp_path: Path, source: str) -> TaskFileService:
    backend_dir = tmp_path / "qubex"
    backend_dir.mkdir()
    (backend_dir / "tasks.py").write_text(source, encoding="utf-8")
    return TaskFileService(calibtasks_base_path=tmp_path)


def test_declared_documentation_takes_precedence_over_docstring(tmp_path: Path) -> None:
    service = _write_backend(tmp_path, DOCUMENTED_TASK_SOURCE)

    tasks = {task.name: task for task in service.list_task_info("qubex").tasks}

    documented = tasks["DocumentedTask"]
    assert documented.description == "Measures something specific."
    assert documented.documentation is not None
    assert documented.documentation.when_to_use == "Run it after the qubit frequency is known."
    assert documented.documentation.prerequisites == (
        "qubit_frequency is stored.",
        "A calibrated readout.",
    )
    assert service.documentation_errors == []


def test_undocumented_task_falls_back_to_docstring(tmp_path: Path) -> None:
    service = _write_backend(tmp_path, DOCUMENTED_TASK_SOURCE)

    legacy = {task.name: task for task in service.list_task_info("qubex").tasks}["LegacyTask"]

    assert legacy.description == "Docstring-only task description."
    assert legacy.documentation is None


@pytest.mark.parametrize(
    ("declaration", "reason"),
    [
        ("DOCS", "literal TaskDocumentation(...) call"),
        ('build_docs(description="x")', "literal TaskDocumentation(...) call"),
        ('TaskDocumentation("positional")', "keyword arguments"),
        ("TaskDocumentation(**DOCS)", "** arguments"),
        ('TaskDocumentation(description=f"{NAME} task")', "must be a string literal"),
        ("TaskDocumentation(description=explode())", "must be a string literal"),
        ('TaskDocumentation(description="")', "description"),
        ('TaskDocumentation(description="x", prerequisites=[1])', "prerequisites.0"),
        ('TaskDocumentation(description="x", next_actions=["y"])', "next_actions"),
        ('TaskDocumentation(description="x", references=["y"])', "references"),
    ],
)
def test_unsupported_documentation_is_rejected_without_executing_the_module(
    tmp_path: Path, declaration: str, reason: str
) -> None:
    source = f'''
raise RuntimeError("task modules must not be imported for metadata")


class BrokenTask:
    """Docstring fallback."""

    name = "BrokenTask"
    documentation = {declaration}
'''
    service = _write_backend(tmp_path, source)

    task = service.list_task_info("qubex").tasks[0]

    assert task.description == "Docstring fallback."
    assert task.documentation is None
    assert len(service.documentation_errors) == 1
    assert service.documentation_errors[0].startswith("tasks.py:BrokenTask: ")
    assert reason in service.documentation_errors[0]


def test_explicit_none_documentation_is_treated_as_undocumented(tmp_path: Path) -> None:
    service = _write_backend(
        tmp_path,
        'class Task:\n    """Doc."""\n\n    name = "Task"\n    documentation = None\n',
    )

    task = service.list_task_info("qubex").tasks[0]

    assert task.description == "Doc."
    assert task.documentation is None
    assert service.documentation_errors == []


def test_catalog_publishes_the_same_documentation_for_fake_and_qubex_tasks() -> None:
    """The fake backend runs qubex classes, so it publishes their documentation unchanged."""
    clear_backend_config_cache()
    qubex = {t.name: t for t in TaskFileService().list_task_info("qubex").tasks}
    fake = {t.name: t for t in TaskFileService().list_task_info("fake").tasks}
    for name, task in fake.items():
        if name in qubex:
            assert task.documentation == qubex[name].documentation, name
    for name in ("CheckChevron", "CheckRabi", "CheckRamsey", "CheckT1"):
        documentation = fake[name].documentation
        assert documentation is not None, name
        assert fake[name].description == documentation.description


# --- Backend path confinement ---

_TASK_SOURCE = 'class {cls}:\n    name: str = "{name}"\n'


def _write_task(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_TASK_SOURCE.format(cls=name, name=name), encoding="utf-8")


@pytest.fixture
def calibtasks(tmp_path: Path) -> Path:
    base = tmp_path / "calibtasks"
    _write_task(base / "fake" / "one_qubit" / "rabi.py", "FakeRabi")
    _write_task(base / "fakeextra" / "secret.py", "SiblingTask")
    _write_task(tmp_path / "outside" / "outside.py", "OutsideTask")
    return base


@pytest.mark.parametrize(
    "backend",
    ["../outside", "..", ".", "", "fake/one_qubit", "fake/../fake", ".hidden", "__pycache__"],
)
def test_list_task_info_rejects_backend_that_is_not_a_single_name(
    calibtasks: Path, backend: str
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        TaskFileService(calibtasks).list_task_info(backend)

    assert exc_info.value.status_code == 400


def test_list_task_info_rejects_absolute_backend(calibtasks: Path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        TaskFileService(calibtasks).list_task_info(str(calibtasks.parent / "outside"))

    assert exc_info.value.status_code == 400


def test_list_task_info_rejects_backend_link_outside_base(calibtasks: Path) -> None:
    (calibtasks / "escape").symlink_to(calibtasks.parent / "outside", target_is_directory=True)

    with pytest.raises(HTTPException) as exc_info:
        TaskFileService(calibtasks).list_task_info("escape")

    assert exc_info.value.status_code == 400


def test_list_task_info_reports_missing_backend(calibtasks: Path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        TaskFileService(calibtasks).list_task_info("missing")

    assert exc_info.value.status_code == 404


def test_list_task_info_reads_only_the_named_backend(calibtasks: Path) -> None:
    """A sibling sharing the name as a prefix ("fakeextra") is not part of "fake"."""
    tasks = TaskFileService(calibtasks).list_task_info("fake").tasks

    assert [(task.name, task.file_path) for task in tasks] == [("FakeRabi", "one_qubit/rabi.py")]


def test_list_task_info_accepts_discovered_backend_without_config(calibtasks: Path) -> None:
    clear_backend_config_cache()
    service = TaskFileService(calibtasks)

    assert "fakeextra" in [backend.name for backend in service.list_backends().backends]
    tasks = service.list_task_info("fakeextra").tasks

    assert [task.name for task in tasks] == ["SiblingTask"]
    assert tasks[0].enabled is False


def test_list_task_info_does_not_follow_links_out_of_backend(calibtasks: Path) -> None:
    backend = calibtasks / "fake"
    outside = calibtasks.parent / "outside"
    (backend / "linked_dir").symlink_to(outside, target_is_directory=True)
    (backend / "linked_file.py").symlink_to(outside / "outside.py")
    (backend / "one_qubit" / "loop").symlink_to(backend, target_is_directory=True)
    (backend / "sibling.py").symlink_to(calibtasks / "fakeextra" / "secret.py")

    tasks = TaskFileService(calibtasks).list_task_info("fake").tasks

    assert [task.name for task in tasks] == ["FakeRabi"]


def test_list_task_info_keeps_file_links_inside_backend(calibtasks: Path) -> None:
    backend = calibtasks / "fake"
    (backend / "alias.py").symlink_to(backend / "one_qubit" / "rabi.py")

    tasks = TaskFileService(calibtasks).list_task_info("fake", sort_order="file_path").tasks

    assert [task.file_path for task in tasks] == ["alias.py", "one_qubit/rabi.py"]


def test_list_task_info_skips_link_cycles(calibtasks: Path) -> None:
    backend = calibtasks / "fake"
    (backend / "alias.py").symlink_to(backend / "one_qubit" / "rabi.py")
    (backend / "self.py").symlink_to("self.py")
    (backend / "ping.py").symlink_to("pong.py")
    (backend / "pong.py").symlink_to("ping.py")
    (backend / "one_qubit" / "loop").symlink_to("loop")

    tasks = TaskFileService(calibtasks).list_task_info("fake", sort_order="file_path").tasks

    assert [(task.name, task.file_path) for task in tasks] == [
        ("FakeRabi", "alias.py"),
        ("FakeRabi", "one_qubit/rabi.py"),
    ]


@pytest.fixture
def swap_backend(calibtasks: Path) -> tuple[Path, Path]:
    """A backend with sibling directories and an outside directory with the same layout."""
    backend = calibtasks / "fake"
    for name in ("a", "b", "c"):
        _write_task(backend / name / "task.py", f"Inside{name.upper()}")
    outside = calibtasks.parent / "outside"
    _write_task(outside / "task.py", "OutsideTask")
    return backend, outside


def test_list_task_info_refuses_backend_replaced_after_validation(
    calibtasks: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = TaskFileService(calibtasks)
    resolve = service._resolve_backend_path

    def resolve_then_swap(backend: str) -> Path:
        checked = resolve(backend)
        checked.rename(calibtasks / "original")
        checked.symlink_to(calibtasks.parent / "outside", target_is_directory=True)
        return checked

    monkeypatch.setattr(service, "_resolve_backend_path", resolve_then_swap)

    assert service.list_task_info("fake").tasks == []


def test_task_discovery_refuses_directory_swapped_for_link_before_descent(
    swap_backend: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, outside = swap_backend
    # "b" is listed as a directory, then swapped for a link while a sibling is read.
    swapped = swap_after_listing(
        monkeypatch, [backend / "a", backend / "c"], swap_dir_for_link(backend / "b", outside)
    )

    tasks = TaskFileService(backend.parent)._collect_tasks_from_directory(backend, backend)

    assert swapped == [True]
    names = {task.name for task in tasks}
    assert "OutsideTask" not in names
    assert {"FakeRabi", "InsideA", "InsideC"} <= names


def test_task_discovery_parses_files_from_the_listed_directory(
    swap_backend: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, outside = swap_backend
    # "b" is swapped for a link after its own entries were listed, before they are parsed.
    swapped = swap_after_listing(
        monkeypatch, [backend / "b"], swap_dir_for_link(backend / "b", outside)
    )

    tasks = TaskFileService(backend.parent)._collect_tasks_from_directory(backend, backend)

    assert swapped == [True]
    assert [(task.name, task.file_path) for task in tasks] == [
        ("InsideA", "a/task.py"),
        ("InsideB", "b/task.py"),
        ("InsideC", "c/task.py"),
        ("FakeRabi", "one_qubit/rabi.py"),
    ]


def test_task_discovery_closes_descriptors_when_stopped_early(
    swap_backend: tuple[Path, Path],
) -> None:
    backend, _ = swap_backend
    baseline = len(os.listdir("/dev/fd"))

    files = TaskFileService(backend.parent)._iter_python_files(backend)
    assert next(files).parts == ("a", "task.py")
    files.close()

    assert len(os.listdir("/dev/fd")) == baseline
