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
    )
