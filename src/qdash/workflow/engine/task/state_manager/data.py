"""Calibration data operations and task type checking functions."""

from typing import Any

from qdash.datamodel.task import CalibDataModel, TaskResultModel


def clear_qubit_calib_data(
    calib_data: CalibDataModel, qid: str, parameter_names: list[str]
) -> None:
    """Clear specific parameters from qubit calibration data.

    Parameters
    ----------
    calib_data : CalibDataModel
        Container for calibration data
    qid : str
        Qubit ID
    parameter_names : list[str]
        Names of parameters to clear

    """
    if qid in calib_data.qubit:
        for name in parameter_names:
            calib_data.qubit[qid].pop(name, None)


def clear_coupling_calib_data(
    calib_data: CalibDataModel, qid: str, parameter_names: list[str]
) -> None:
    """Clear specific parameters from coupling calibration data.

    Parameters
    ----------
    calib_data : CalibDataModel
        Container for calibration data
    qid : str
        Qubit ID (coupling ID like "0-1")
    parameter_names : list[str]
        Names of parameters to clear

    """
    if qid in calib_data.coupling:
        for name in parameter_names:
            calib_data.coupling[qid].pop(name, None)


def get_qubit_calib_data(calib_data: CalibDataModel, qid: str) -> dict[Any, Any]:
    """Get calibration data for a qubit.

    Parameters
    ----------
    calib_data : CalibDataModel
        Container for calibration data
    qid : str
        Qubit ID

    Returns
    -------
    dict
        The qubit calibration data

    """
    return dict(calib_data.qubit.get(qid, {}))


def get_coupling_calib_data(calib_data: CalibDataModel, qid: str) -> dict[Any, Any]:
    """Get calibration data for a coupling.

    Parameters
    ----------
    calib_data : CalibDataModel
        Container for calibration data
    qid : str
        Coupling ID

    Returns
    -------
    dict
        The coupling calibration data

    """
    return dict(calib_data.coupling.get(qid, {}))


def has_only_qubit_or_global_tasks(task_result: TaskResultModel, task_names: list[str]) -> bool:
    """Check if all tasks are qubit or global types only.

    Parameters
    ----------
    task_result : TaskResultModel
        Container for all task results
    task_names : list[str]
        Names of tasks to check

    Returns
    -------
    bool
        True if all tasks are qubit or global types

    """
    for name in task_names:
        # Check in global tasks
        if any(t.name == name for t in task_result.global_tasks):
            continue
        # Check in any qubit tasks
        found = False
        for qubit_tasks in task_result.qubit_tasks.values():
            if any(t.name == name for t in qubit_tasks):
                found = True
                break
        if not found:
            # Check if it's a coupling task
            for coupling_tasks in task_result.coupling_tasks.values():
                if any(t.name == name for t in coupling_tasks):
                    return False
    return True


def has_only_coupling_or_global_tasks(task_result: TaskResultModel, task_names: list[str]) -> bool:
    """Check if all tasks are coupling or global types only.

    Parameters
    ----------
    task_result : TaskResultModel
        Container for all task results
    task_names : list[str]
        Names of tasks to check

    Returns
    -------
    bool
        True if all tasks are coupling or global types

    """
    for name in task_names:
        # Check in global tasks
        if any(t.name == name for t in task_result.global_tasks):
            continue
        # Check in any coupling tasks
        found = False
        for coupling_tasks in task_result.coupling_tasks.values():
            if any(t.name == name for t in coupling_tasks):
                found = True
                break
        if not found:
            # Check if it's a qubit task
            for qubit_tasks in task_result.qubit_tasks.values():
                if any(t.name == name for t in qubit_tasks):
                    return False
    return True


def has_only_system_tasks(task_result: TaskResultModel, task_names: list[str]) -> bool:
    """Check if all tasks are system types only.

    Parameters
    ----------
    task_result : TaskResultModel
        Container for all task results
    task_names : list[str]
        Names of tasks to check

    Returns
    -------
    bool
        True if all tasks are system types

    """
    return all(any(t.name == name for t in task_result.system_tasks) for name in task_names)
