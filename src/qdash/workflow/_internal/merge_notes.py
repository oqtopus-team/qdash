from typing import Any

import pendulum


def merge_notes_by_timestamp(
    master_note: dict[str, Any], task_note: dict[str, Any]
) -> dict[str, Any]:
    """Merge master note and task note based on timestamp for each parameter type and qubit.

    Args:
    ----
        master_note: Master note to merge into
        task_note: Task note to merge from

    Returns:
    -------
        Merged note with most recent values

    """
    merged: dict[str, Any] = {}

    # Get all parameter types (hpi_params, pi_params, rabi_params)
    all_param_types = set(master_note.keys()) | set(task_note.keys())

    for param_type in all_param_types:
        merged[param_type] = {}

        # Get all qubits for this parameter type
        all_qubits = set(master_note.get(param_type, {}).keys()) | set(
            task_note.get(param_type, {}).keys()
        )

        for qubit in all_qubits:
            master_data = master_note.get(param_type, {}).get(qubit)
            task_data = task_note.get(param_type, {}).get(qubit)

            # If qubit exists only in one note, use that data
            if not master_data:
                merged[param_type][qubit] = task_data
                continue
            if not task_data:
                merged[param_type][qubit] = master_data
                continue

            # Compare timestamps to determine which data to use
            master_time = pendulum.from_format(master_data["timestamp"], "YYYY-MM-DD HH:mm:ss")
            task_time = pendulum.from_format(task_data["timestamp"], "YYYY-MM-DD HH:mm:ss")

            merged[param_type][qubit] = task_data if task_time > master_time else master_data

    return merged
