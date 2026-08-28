"""Tests for forwarding qubex tqdm progress into QDash."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from qdash.workflow.engine.backend.plugins.qubex_progress import capture_qubex_progress

if TYPE_CHECKING:
    from qdash.workflow.engine.progress import TaskProgress


def test_capture_qubex_progress_reports_completion() -> None:
    """The patched qubex tqdm should emit a final snapshot with zero ETA."""
    from qubex.experiment.services import characterization_service

    events: list[TaskProgress] = []

    with capture_qubex_progress(events.append):
        for _ in characterization_service.tqdm(
            range(3),
            desc="control power sweep for Q00",
            file=StringIO(),
        ):
            pass

    assert events
    assert events[-1].current == 3
    assert events[-1].total == 3
    assert events[-1].description == "control power sweep for Q00"
    assert events[-1].eta_seconds == 0.0
    assert events[-1].updated_at


def test_capture_qubex_progress_reports_before_first_iteration() -> None:
    """A long-running first sweep point should still show initial progress."""
    from qubex.experiment.services import characterization_service

    events: list[TaskProgress] = []
    with capture_qubex_progress(events.append, task_name="CheckQubitSpectroscopy"):
        progress = characterization_service.tqdm(
            range(3),
            desc="control power sweep for Q00",
            file=StringIO(),
        )
        assert events[-1].current == 0
        assert events[-1].total == 3
        progress.close()


def test_capture_qubex_progress_patches_measurement_service() -> None:
    """Measurement-service experiments should use the same progress adapter."""
    from qubex.experiment.services import measurement_service

    events: list[TaskProgress] = []
    with capture_qubex_progress(events.append):
        list(
            measurement_service.tqdm(
                range(2),
                desc="Sweeping parameters",
                disable=True,
                file=StringIO(),
            )
        )

    assert events[-1].current == 2
    assert events[-1].description == "Sweeping parameters"


def test_rabi_progress_labels_disabled_qubex_sweep() -> None:
    """Disabled internal bars should count and receive a task-specific label."""
    from qubex.experiment.services import measurement_service

    events: list[TaskProgress] = []
    with capture_qubex_progress(events.append, task_name="CheckRabi"):
        list(
            measurement_service.tqdm(
                range(4),
                desc="Sweeping parameters",
                disable=True,
                file=StringIO(),
            )
        )

    assert events[0].current == 0
    assert events[-1].current == 4
    assert events[-1].total == 4
    assert {event.description for event in events} == {"Rabi time sweep"}


def test_capture_qubex_progress_is_scoped_to_context() -> None:
    """A reporter should not receive tqdm events after its context exits."""
    from qubex.experiment.services import characterization_service

    events: list[TaskProgress] = []
    with capture_qubex_progress(events.append):
        list(characterization_service.tqdm(range(1), file=StringIO()))

    reported_count = len(events)
    list(characterization_service.tqdm(range(1), file=StringIO()))

    assert len(events) == reported_count


def test_capture_qubex_progress_ignores_nested_bars() -> None:
    """Nested qubex bars must not reset the task's outer progress."""
    from qubex.experiment.services import characterization_service

    events: list[TaskProgress] = []
    with capture_qubex_progress(events.append):
        for _ in characterization_service.tqdm(range(2), desc="outer sweep", file=StringIO()):
            list(characterization_service.tqdm(range(3), desc="inner sweep", file=StringIO()))

    assert events
    assert {event.description for event in events} == {"outer sweep"}
    assert events[-1].current == 2
    assert events[-1].total == 2


def test_qubit_spectroscopy_reports_only_control_power_sweep() -> None:
    """Qubit spectroscopy should hide its frequency subrange implementation."""
    from qubex.experiment.services import characterization_service

    events: list[TaskProgress] = []
    with capture_qubex_progress(events.append, task_name="CheckQubitSpectroscopy"):
        list(
            characterization_service.tqdm(
                range(2), desc="qubit freq. scan subranges for Q00", file=StringIO()
            )
        )
        list(
            characterization_service.tqdm(
                range(3), desc="control power sweep for Q00", file=StringIO()
            )
        )

    assert events
    assert {event.description for event in events} == {"control power sweep for Q00"}
    assert events[-1].current == 3


def test_resonator_spectroscopy_ignores_setup_and_subrange_bars() -> None:
    """Resonator spectroscopy should report only its readout power sweep."""
    from qubex.experiment.services import characterization_service

    events: list[TaskProgress] = []
    with capture_qubex_progress(events.append, task_name="CheckResonatorSpectroscopy"):
        list(
            characterization_service.tqdm(
                range(2), desc="electrical delay for Q00", file=StringIO()
            )
        )
        list(
            characterization_service.tqdm(
                range(4), desc="resonator freq. scan subranges for Q00", file=StringIO()
            )
        )
        list(characterization_service.tqdm(range(5), file=StringIO()))

    assert events
    assert {event.description for event in events} == {"readout power sweep"}
    assert events[-1].current == 5
