import json
from typing import Any, ClassVar, Dict

import numpy as np
from qdash.workflow.tasks.base import (
    BaseTask,
    InputParameter,
    OutputParameter,
    PostProcessResult,
    PreProcessResult,
    RunResult,
)
from qdash.workflow.utils.task_converter import convert_json_to_task_parameters
from qubex.experiment import Experiment
from qubex.experiment.experiment import RABI_TIME_RANGE
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class DynamicCheckRabi(BaseTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRabi"
    task_type: str = "qubit"
    input_parameters: ClassVar[dict[str, InputParameter]] = {
        "time_range": InputParameter(
            unit="ns",
            value_type="ndarray",
            value=RABI_TIME_RANGE,
            description="Time range for Rabi oscillation",
        ),
        "shots": InputParameter(
            unit="",
            value_type="int",
            value=DEFAULT_SHOTS,
            description="Number of shots for Rabi oscillation",
        ),
        "interval": InputParameter(
            unit="ns",
            value_type="int",
            value=DEFAULT_INTERVAL,
            description="Time interval for Rabi oscillation",
        ),
    }
    output_parameters: ClassVar[dict[str, OutputParameter]] = {
        "rabi_amplitude": OutputParameter(unit="a.u.", description="Rabi oscillation amplitude"),
        "rabi_frequency": OutputParameter(unit="GHz", description="Rabi oscillation frequency"),
    }

    def __init__(self, params: Dict[str, Any]) -> None:
        """Initialize the task with parameters.

        Args:
        ----
            params: Dictionary containing task parameters

        """
        super().__init__()

        # Convert parameters
        converted = convert_json_to_task_parameters(params)

        # Set input parameter values
        self.input_parameters["time_range"].value = converted["input_parameters"]["time_range"][
            "value"
        ]
        self.input_parameters["shots"].value = converted["input_parameters"]["shots"]["value"]
        self.input_parameters["interval"].value = converted["input_parameters"]["interval"]["value"]

    def preprocess(self, exp: Experiment, qid: str) -> PreProcessResult:
        """Preprocess the task."""
        input_param = {
            "time_range": self.input_parameters["time_range"],
            "shots": self.input_parameters["shots"],
            "interval": self.input_parameters["interval"],
        }
        return PreProcessResult(input_parameters=input_param)

    def postprocess(self, execution_id: str, run_result: RunResult, qid: str) -> PostProcessResult:
        """Required by BaseTask but not used in this example."""
        return PostProcessResult(output_parameters={}, figures=[], raw_data=[])

    def run(self, exp: Experiment, qid: str) -> RunResult:
        """Required by BaseTask but not used in this example."""
        return RunResult(raw_result=None)


def main():
    # Load JSON file into dictionary
    with open("check_rabi.json") as f:
        params = json.load(f)

    # Create task with parameters dictionary
    task = DynamicCheckRabi(params)

    # Print task information
    print("\nInput Parameters:")
    for name, param in task.input_parameters.items():
        print(f"\n{name}:")
        print(f"  Unit: {param.unit}")
        print(f"  Value Type: {param.value_type}")
        print(f"  Value: {param.value}")
        if param.value_type == "ndarray":
            print(f"  Value Type (actual): {type(param.value)}")
            if isinstance(param.value, np.ndarray):
                print(f"  Shape: {param.value.shape}")
        print(f"  Description: {param.description}")

    print("\nOutput Parameters:")
    for name, param in task.output_parameters.items():
        print(f"\n{name}:")
        print(f"  Unit: {param.unit}")
        print(f"  Description: {param.description}")


if __name__ == "__main__":
    main()
