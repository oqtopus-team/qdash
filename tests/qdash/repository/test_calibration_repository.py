from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from qdash.repository.coupling import MongoCouplingCalibrationRepository
from qdash.repository.qubit import MongoQubitCalibrationRepository


def _query_result(value: object) -> MagicMock:
    result = MagicMock()
    result.run.return_value = value
    return result


def test_qubit_update_lookup_falls_back_to_legacy_username_document() -> None:
    legacy_doc = SimpleNamespace(data={"frequency": {"value": 5.0}})
    with patch("qdash.repository.qubit.QubitDocument.find_one") as find_one:
        find_one.side_effect = [_query_result(None), _query_result(legacy_doc)]

        data = MongoQubitCalibrationRepository().get_calibration_data_for_update(
            username="alice", project_id="project-1", chip_id="chip-1", qid="1"
        )

    assert data == {"frequency": {"value": 5.0}}
    assert find_one.call_args_list[0].args[0] == {
        "project_id": "project-1",
        "chip_id": "chip-1",
        "qid": "1",
    }
    assert find_one.call_args_list[1].args[0] == {
        "username": "alice",
        "chip_id": "chip-1",
        "qid": "1",
    }


def test_coupling_update_lookup_prefers_project_document() -> None:
    project_doc = SimpleNamespace(data={"coupling_strength": {"value": 0.02}})
    with patch("qdash.repository.coupling.CouplingDocument.find_one") as find_one:
        find_one.return_value = _query_result(project_doc)

        data = MongoCouplingCalibrationRepository().get_calibration_data_for_update(
            username="alice", project_id="project-1", chip_id="chip-1", qid="0-1"
        )

    assert data == {"coupling_strength": {"value": 0.02}}
    find_one.assert_called_once_with({"project_id": "project-1", "chip_id": "chip-1", "qid": "0-1"})
