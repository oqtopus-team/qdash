from unittest.mock import MagicMock, patch

import pytest

from qdash.workflow.service.targets import MuxTargets, QubitTargets


@pytest.mark.parametrize("targets", [MuxTargets([0]), QubitTargets(["0", "1"])])
def test_database_backed_coupling_targets_require_project_id(targets) -> None:
    with pytest.raises(ValueError, match="project_id is required"):
        targets.to_coupling_ids("chip-1")


def test_qubit_targets_pass_project_id_to_cr_scheduler() -> None:
    scheduler = MagicMock()
    scheduler.generate.return_value.parallel_groups = [[("0", "1")]]

    with patch("qdash.workflow.engine.CRScheduler", return_value=scheduler) as scheduler_cls:
        result = QubitTargets(["0", "1"]).to_coupling_ids("chip-1", project_id="proj-1")

    assert result == ["0-1"]
    scheduler_cls.assert_called_once_with(
        username="",
        chip_id="chip-1",
        wiring_config_path="/app/config/qubex-config/chip-1/config/wiring.yaml",
        project_id="proj-1",
        mux_mapping=None,
    )


def test_mux_targets_schedule_pairs_among_resolved_qids_on_given_mapping() -> None:
    scheduler = MagicMock()
    scheduler.generate.return_value.parallel_groups = [[("0", "1"), ("2", "3")], [("1", "2")]]
    mapping = MagicMock()

    with (
        patch.object(MuxTargets, "to_qids", return_value=["0", "1", "2", "3"]) as to_qids,
        patch("qdash.workflow.engine.CRScheduler", return_value=scheduler) as scheduler_cls,
    ):
        result = MuxTargets([0]).to_coupling_ids("chip-1", project_id="proj-1", mux_mapping=mapping)

    assert result == ["0-1", "2-3", "1-2"]
    to_qids.assert_called_once_with("chip-1", mux_mapping=mapping)
    assert scheduler_cls.call_args.kwargs["mux_mapping"] is mapping
    scheduler.generate.assert_called_once_with(
        candidate_qubits=["0", "1", "2", "3"], max_parallel_ops=100
    )
