"""Workflow helper functions and utilities for Python Flow Editor."""

from qdash.workflow.helpers.flow_helpers import (
    FlowSession,
    adaptive_calibrate,
    calibrate_qubits_parallel,
    calibrate_qubits_qubit_first,
    calibrate_qubits_serial,
    calibrate_qubits_task_first,
    execute_schedule,
    finish_calibration,
    generate_execution_id,
    get_session,
    init_calibration,
)
from qdash.workflow.helpers.parallel_helpers import calibrate_parallel, parallel_map

__all__ = [
    # === Session Management ===
    "FlowSession",
    "init_calibration",
    "get_session",
    "finish_calibration",
    "generate_execution_id",
    # === Parallel Execution (Recommended) ===
    "calibrate_parallel",  # True parallel execution across qubits using @task + submit
    "parallel_map",  # Generic parallel map for custom logic with Prefect UI visibility
    # === Sequential Execution ===
    "calibrate_qubits_task_first",  # Task1→all qubits, Task2→all qubits, ...
    "calibrate_qubits_qubit_first",  # Q0→all tasks, Q1→all tasks, ...
    "execute_schedule",  # Custom orchestration using SerialNode/ParallelNode/BatchNode
    # === Adaptive Calibration ===
    "adaptive_calibrate",  # Single qubit closed-loop helper
    # === Deprecated (Backward Compatibility) ===
    "calibrate_qubits_parallel",  # DEPRECATED: Alias for task_first (NOT truly parallel)
    "calibrate_qubits_serial",  # DEPRECATED: Alias for qubit_first
]
