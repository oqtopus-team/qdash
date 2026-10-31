"""FakeBringUp publishes the simulator's device parameters."""

from __future__ import annotations

import pytest

from qdash.workflow.calibtasks.fake.fake_bring_up import FakeBringUp
from qdash.workflow.engine.backend.fake import FakeBackend


def test_bring_up_publishes_the_simulated_device_parameters() -> None:
    task = FakeBringUp()
    backend = FakeBackend({})
    exp = backend.get_instance()
    label = exp.get_qubit_label(1)

    run_result = task.run(backend, "1")
    result = task.postprocess(backend, execution_id="exec-1", run_result=run_result, qid="1")

    outputs = result.output_parameters
    assert outputs["qubit_frequency"].value == pytest.approx(exp.get_target(label).frequency)
    assert outputs["resonator_frequency"].value == pytest.approx(
        exp.get_target(exp.get_resonator_label(1)).frequency
    )
    assert outputs["readout_frequency"].value == outputs["resonator_frequency"].value
    assert outputs["readout_amplitude"].value == pytest.approx(
        exp.control_params.get_readout_amplitude(label)
    )
    assert outputs["control_amplitude"].value == pytest.approx(
        exp.control_params.get_control_amplitude(label)
    )
    assert all(parameter.execution_id == "exec-1" for parameter in outputs.values())
    assert len(result.figures) == 1


def test_bring_up_refuses_a_non_fake_experiment() -> None:
    class HardwareBackend:
        def get_instance(self) -> object:
            return object()

    with pytest.raises(RuntimeError, match="only runs on the fake backend"):
        FakeBringUp().run(HardwareBackend(), "0")  # type: ignore[arg-type]
