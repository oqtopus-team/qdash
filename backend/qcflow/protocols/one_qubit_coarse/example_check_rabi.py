import json
from pathlib import Path

import numpy as np
from qcflow.protocols.one_qubit_coarse.check_rabi import CheckRabi


def main():
    # Example MongoDB-style parameters
    params = {
        "name": "CheckRabi",
        "task_type": "qubit",
        "input_parameters": {
            "time_range": {
                "unit": "ns",
                "value_type": "ndarray",
                "value": [0, 201, 4],
                "description": "Time range for Rabi oscillation",
            },
            "shots": {
                "unit": "",
                "value_type": "int",
                "value": 1024,
                "description": "Number of shots for Rabi oscillation",
            },
            "interval": {
                "unit": "ns",
                "value_type": "int",
                "value": "150 * 1024",
                "description": "Time interval for Rabi oscillation",
            },
        },
    }

    # Create task instance with parameters
    task = CheckRabi(params)

    # Print and verify parameters
    print("\nInput Parameters:")
    for name, param in task.input_parameters.items():
        print(f"\n{name}:")
        print(f"  Unit: {param.unit}")
        print(f"  Value Type: {param.value_type}")
        print(f"  Value: {param.value}")

        # Verify parameter conversions
        if name == "time_range":
            assert isinstance(param.value, range)
            assert list(param.value) == list(
                range(0, 201, 4)
            ), "time_range should be range(0, 201, 4)"
            print(f"  Value Type (actual): {type(param.value)}")
        elif name == "shots":
            assert isinstance(param.value, int)
            assert param.value == 1024, "shots should be 1024"
        elif name == "interval":
            assert isinstance(param.value, int)
            assert param.value == 150 * 1024, "interval should be 150 * 1024"

        print(f"  Description: {param.description}")

    print("\nOutput Parameters:")
    for name, param in task.output_parameters.items():
        print(f"\n{name}:")
        print(f"  Unit: {param.unit}")
        print(f"  Description: {param.description}")

    # Test JSON serialization
    print("\nTesting JSON serialization:")
    try:
        # Convert task parameters to JSON
        serialized = json.dumps(task.input_parameters["time_range"].model_dump(), indent=2)
        print("\nSerialized time_range parameter:")
        print(serialized)

        # Verify the serialized data
        deserialized = json.loads(serialized)
        assert isinstance(deserialized["value"], list), "Serialized value should be a list"
        assert deserialized["value"] == [0, 201, 4], "Serialized value should match original list"
        print("\nJSON serialization test passed!")
    except Exception as e:
        print(f"\nJSON serialization test failed: {e}")

    print("\nAll tests passed successfully!")


if __name__ == "__main__":
    main()
