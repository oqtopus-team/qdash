import pytest

from qdash.workflow.calibtasks.qubex.one_qubit_coarse.check_rabi import CheckRabi
from qdash.workflow.engine.task.result_processor import R2ValidationError, TaskResultProcessor


def test_check_rabi_uses_r2_threshold_0_6() -> None:
    task = CheckRabi()
    processor = TaskResultProcessor()

    assert task.r2_threshold == 0.6
    assert processor.validate_r2({"0": 0.61}, "0", task.r2_threshold) is True
    with pytest.raises(R2ValidationError):
        processor.validate_r2({"0": 0.59}, "0", task.r2_threshold)
