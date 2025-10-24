"""Dynamic flow executor for user-defined flows.

This module provides utilities to dynamically load and execute Prefect flows
from Python files stored in the user_flows directory.
"""

import importlib.util
import sys
from logging import getLogger
from pathlib import Path
from typing import Any

from prefect import Flow

logger = getLogger(__name__)


class FlowExecutionError(Exception):
    """Exception raised during flow execution."""

    pass


def load_flow_from_file(file_path: str, flow_name: str) -> Flow:
    """Load a Prefect Flow from a Python file.

    Args:
    ----
        file_path: Absolute or relative path to .py file
        flow_name: Name of the flow function (must be decorated with @flow)

    Returns:
    -------
        Prefect Flow object

    Raises:
    ------
        FlowExecutionError: If file not found, flow not found, or not a valid Flow

    """
    file_path = Path(file_path).resolve()

    if not file_path.exists():
        raise FlowExecutionError(f"Flow file not found: {file_path}")

    # Generate unique module name to avoid conflicts
    module_name = f"dynamic_flow_{file_path.stem}_{id(file_path)}"

    try:
        # Load module from file
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise FlowExecutionError(f"Cannot load module from {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Get flow function
        if not hasattr(module, flow_name):
            available = [name for name in dir(module) if not name.startswith("_")]
            raise FlowExecutionError(
                f"Flow function '{flow_name}' not found in {file_path}. " f"Available: {available}"
            )

        flow_func = getattr(module, flow_name)

        # Verify it's a Prefect Flow
        if not isinstance(flow_func, Flow):
            raise FlowExecutionError(f"'{flow_name}' is not a Prefect Flow. " f"Make sure it's decorated with @flow")

        logger.info(f"Successfully loaded flow '{flow_name}' from {file_path}")
        return flow_func

    except Exception as e:
        if isinstance(e, FlowExecutionError):
            raise
        raise FlowExecutionError(f"Error loading flow: {e}") from e
    finally:
        # Clean up module from sys.modules to avoid conflicts
        if module_name in sys.modules:
            del sys.modules[module_name]


def execute_flow_from_file(file_path: str, flow_name: str, parameters: dict[str, Any]) -> Any:
    """Execute a Prefect Flow from a file with given parameters.

    Args:
    ----
        file_path: Path to .py file
        flow_name: Name of flow function
        parameters: Parameters to pass to the flow

    Returns:
    -------
        Flow execution result

    Raises:
    ------
        FlowExecutionError: If execution fails

    """
    try:
        # Load flow
        flow = load_flow_from_file(file_path, flow_name)

        # Execute flow
        logger.info(f"Executing flow '{flow_name}' with parameters: {parameters}")
        result = flow(**parameters)

        logger.info(f"Flow '{flow_name}' completed successfully")
        return result

    except Exception as e:
        logger.error(f"Flow execution failed: {e}")
        if isinstance(e, FlowExecutionError):
            raise
        raise FlowExecutionError(f"Flow execution failed: {e}") from e
