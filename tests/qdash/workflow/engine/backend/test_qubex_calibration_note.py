"""Qubex calibration-note persistence keeps transition-specific entries."""

import json
from unittest.mock import MagicMock

import pytest

from qdash.workflow.engine.backend.qubex import QubexBackend


def test_update_note_keeps_base_and_transition_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = QubexBackend({})
    repository = MagicMock()
    backend._calibration_note_repo = repository
    monkeypatch.setattr(
        backend,
        "get_note",
        lambda: json.dumps(
            {
                "rabi_params": {
                    "Q00": {"r2": 0.9},
                    "Q00-ef": {"r2": 0.95},
                    "Q00-fh": {"r2": 0.94},
                    "Q01-ef": {},
                },
                "hpi_params": {"Q00-ef": {"amplitude": 0.2}, "Q01-ef": {}},
                "state_params": {"Q00": {"centers": {}}, "Q01": {}},
                "cr_params": {"Q00-Q01": {"duration": 128}},
            }
        ),
    )
    monkeypatch.setattr(
        "qdash.common.domain.qubit.qid_to_label_from_chip",
        lambda *_args, **_kwargs: "Q00",
    )

    backend.update_note(
        username="alice",
        chip_id="chip",
        calib_dir="/tmp/calib",
        execution_id="exec",
        task_manager_id="manager",
        project_id="project",
        qid="0",
    )

    saved = repository.merge_note_fields.call_args.kwargs["calib_note"]
    assert saved == {
        "rabi_params": {
            "Q00": {"r2": 0.9},
            "Q00-ef": {"r2": 0.95},
            "Q00-fh": {"r2": 0.94},
        },
        "hpi_params": {"Q00-ef": {"amplitude": 0.2}},
        "state_params": {"Q00": {"centers": {}}},
    }
