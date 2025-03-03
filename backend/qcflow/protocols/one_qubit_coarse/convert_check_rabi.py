import json
from typing import Any, ClassVar

import numpy as np
from qcflow.protocols.base import BaseTask, InputParameter, OutputParameter
from qcflow.utils.task_converter import convert_json_to_task_parameters
from qubex.experiment import Experiment
from qubex.experiment.experiment import RABI_TIME_RANGE
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS


class DynamicCheckRabi(BaseTask):
    """Task to check the Rabi oscillation."""

    name: str = "CheckRabi"
    task_type: str = "qubit"

    def __init__(self, json_path: str) -> None:
        """Initialize the task from JSON configuration.

        Args:
        ----
            json_path: Path to the JSON configuration file

        """
        # Read and convert JSON parameters
        with open(json_path) as f:
            json_data = json.load(f)
        converted = convert_json_to_task_parameters(json_data)

        # Set up input parameters
        self.input_parameters: dict[str, InputParameter] = {
            name: InputParameter(**param) for name, param in converted["input_parameters"].items()
        }

        # Set up output parameters
        self.output_parameters: ClassVar[dict[str, OutputParameter]] = {
            name: OutputParameter(**param) for name, param in converted["output_parameters"].items()
        }

        # Initialize with default values
        super().__init__()
        self.input_parameters["time_range"].value = RABI_TIME_RANGE
        self.input_parameters["shots"].value = DEFAULT_SHOTS
        self.input_parameters["interval"].value = DEFAULT_INTERVAL

    def preprocess(self, exp: Experiment, qid: str) -> Any:
        """Required by BaseTask but not used in this example."""

    def postprocess(self, execution_id: str, run_result: Any, qid: str) -> Any:
        """Required by BaseTask but not used in this example."""

    def run(self, exp: Experiment, qid: str) -> Any:
        """Required by BaseTask but not used in this example."""


def main():
    # Create task from JSON
    task = DynamicCheckRabi("check_rabi.json")

    # Print the converted parameters to verify
    print("\nConverted Input Parameters:")
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

    print("\nConverted Output Parameters:")
    for name, param in task.output_parameters.items():
        print(f"\n{name}:")
        print(f"  Unit: {param.unit}")
        print(f"  Description: {param.description}")


if __name__ == "__main__":
    main()
