"""Calibration data operations and task type checking functions."""

from collections.abc import Mapping, Sequence
from typing import Any

from qdash.datamodel.task import CalibDataModel, ParameterModel, TaskResultModel


def expand_published_parameters(
    output_parameters: Mapping[str, ParameterModel],
    publish_targets: Mapping[str, Sequence[str]] | None,
) -> dict[str, ParameterModel]:
    """Key output parameters by the calibration parameter names they publish.

    Parameters
    ----------
    output_parameters : Mapping[str, ParameterModel]
        Task outputs keyed by output name
    publish_targets : Mapping[str, Sequence[str]] | None
        Published parameter names per output name. An output that is missing
        from the mapping, or has no targets, publishes under its own name.

    Returns
    -------
    dict[str, ParameterModel]
        Parameters keyed by published name. A target that differs from the
        output name receives a copy carrying that name as ``parameter_name``.

    """
    published: dict[str, ParameterModel] = {}
    for output_name, parameter in output_parameters.items():
        targets = tuple(publish_targets.get(output_name, ())) if publish_targets else ()
        for target in targets or (output_name,):
            if target in published:
                raise ValueError(f"Multiple outputs publish to '{target}'")
            if target == output_name:
                published[target] = parameter
            else:
                published[target] = parameter.model_copy(update={"parameter_name": target})
    return published


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
