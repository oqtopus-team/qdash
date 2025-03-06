from typing import Any, Dict

import numpy as np


def convert_value(value: Any, value_type: str) -> Any:
    """Convert a value to the specified type.

    Args:
    ----
        value: The value to convert
        value_type: The target type to convert to

    Returns:
    -------
        The converted value

    """
    if value_type == "ndarray":
        if isinstance(value, list):
            return np.array(value)
        elif isinstance(value, str):
            try:
                # Try to evaluate as a list
                value = eval(value)  # Safe here since we control the input format
                return np.array(value)
            except (ValueError, SyntaxError):
                # Try parsing as comma-separated values
                value = [float(x.strip()) for x in value.strip("[]").split(",")]
                return np.array(value)
        return np.array(value)
    elif value_type == "int":
        if isinstance(value, str) and "*" in value:
            # Handle expressions like "150 * 1024"
            parts = [int(p.strip()) for p in value.split("*")]
            result = 1
            for p in parts:
                result *= p
            return result
        return int(value)
    elif value_type == "float":
        return float(value)
    return value


def convert_json_to_task_parameters(json_data: dict) -> dict[str, dict]:
    """Convert JSON task parameters to the format expected by Pydantic models.

    Args:
    ----
        json_data: The JSON data containing task parameters

    Returns:
    -------
        Dictionary with converted input and output parameters

    """
    input_params = {}
    output_params = {}

    # Convert input parameters
    for param in json_data.get("input_parameters", []):
        value = convert_value(param["value"], param["value_type"])
        input_params[param["name"]] = {
            "unit": param.get("unit", ""),
            "value_type": param["value_type"],
            "value": value,
            "description": param["description"],
        }

    # Convert output parameters
    for param in json_data.get("output_parameters", []):
        output_params[param["name"]] = {
            "unit": param.get("unit", ""),
            "description": param["description"],
        }

    return {"input_parameters": input_params, "output_parameters": output_params}
