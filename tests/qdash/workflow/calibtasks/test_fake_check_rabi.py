import numpy as np

from qdash.workflow.calibtasks.base import RunResult
from qdash.workflow.calibtasks.fake.fake_check_rabi import FakeCheckRabi
from qdash.workflow.engine.backend.fake import FakeBackend


def test_fake_check_rabi_outputs_control_amplitude():
    """Fake CheckRabi should emit control_amplitude for params YAML verification."""
    task = FakeCheckRabi()
    backend = FakeBackend({})

    result = task.postprocess(
        backend,
        execution_id="exec-1",
        run_result=RunResult(
            raw_result={
                "rabi_amplitude": 0.45,
                "rabi_frequency": 12.0,
                "rabi_phase": 0.0,
                "rabi_offset": 0.5,
                "time": np.array([0, 8, 16]),
                "signal": np.array([0.9, 0.8, 0.7]),
            },
            r2={"0": 0.98},
        ),
        qid="0",
    )

    control_amplitude = result.output_parameters["control_amplitude"]
    maximum_rabi_frequency = result.output_parameters["maximum_rabi_frequency"]

    assert maximum_rabi_frequency.value == 960.0
    assert control_amplitude.value == 0.0125 / 0.96
    assert control_amplitude.execution_id == "exec-1"
