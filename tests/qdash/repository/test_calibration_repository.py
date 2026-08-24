from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.repository.coupling import MongoCouplingCalibrationRepository
from qdash.repository.qubit import MongoQubitCalibrationRepository


def _query_result(value: object) -> MagicMock:
    result = MagicMock()
    result.run.return_value = value
    return result


def test_qubit_update_lookup_does_not_fall_back_outside_project() -> None:
    with patch("qdash.repository.qubit.QubitDocument.find_one") as find_one:
        find_one.return_value = _query_result(None)

        data = MongoQubitCalibrationRepository().get_calibration_data_for_update(
            username="alice", project_id="project-1", chip_id="chip-1", qid="1"
        )

    assert data == {}
    find_one.assert_called_once_with(
        {
            "project_id": "project-1",
            "chip_id": "chip-1",
            "qid": "1",
        }
    )


def test_qubit_update_lookup_uses_legacy_scope_without_project() -> None:
    legacy_doc = SimpleNamespace(data={"frequency": {"value": 5.0}})
    with patch("qdash.repository.qubit.QubitDocument.find_one") as find_one:
        find_one.return_value = _query_result(legacy_doc)

        data = MongoQubitCalibrationRepository().get_calibration_data_for_update(
            username="alice", project_id=None, chip_id="chip-1", qid="1"
        )

    assert data == {"frequency": {"value": 5.0}}
    find_one.assert_called_once_with({"username": "alice", "chip_id": "chip-1", "qid": "1"})


def test_coupling_update_lookup_prefers_project_document() -> None:
    project_doc = SimpleNamespace(data={"coupling_strength": {"value": 0.02}})
    with patch("qdash.repository.coupling.CouplingDocument.find_one") as find_one:
        find_one.return_value = _query_result(project_doc)

        data = MongoCouplingCalibrationRepository().get_calibration_data_for_update(
            username="alice", project_id="project-1", chip_id="chip-1", qid="0-1"
        )

    assert data == {"coupling_strength": {"value": 0.02}}
    find_one.assert_called_once_with({"project_id": "project-1", "chip_id": "chip-1", "qid": "0-1"})


@pytest.mark.parametrize(
    ("document", "qid", "label"),
    [
        (QubitDocument, "1", "Qubit"),
        (CouplingDocument, "0-1", "Coupling"),
    ],
)
def test_document_update_does_not_fall_back_outside_project(
    document: type[QubitDocument] | type[CouplingDocument], qid: str, label: str
) -> None:
    with patch.object(document, "find_one") as find_one:
        find_one.return_value = _query_result(None)

        with pytest.raises(ValueError, match=label):
            document.update_calib_data(
                username="alice",
                qid=qid,
                chip_id="chip-1",
                output_parameters={"frequency": {"value": 5.0}},
                project_id="project-1",
            )

    find_one.assert_called_once_with({"project_id": "project-1", "qid": qid, "chip_id": "chip-1"})
