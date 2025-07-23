import re

from prefect import task
from pydantic import BaseModel
from qdash.datamodel.parameter import ParameterModel
from qdash.datamodel.task import TaskModel
from qdash.workflow.tasks.base import BaseTask


def qid_to_label(qid: str) -> str:
    """Convert a numeric qid string to a label with at least two digits. e.g. '0' -> 'Q00'."""
    if re.fullmatch(r"\d+", qid):
        return "Q" + qid.zfill(2)
    error_message = "Invalid qid format."
    raise ValueError(error_message)


def pydantic_serializer(obj: BaseModel) -> dict:
    """Serialize a Pydantic BaseModel instance to a dictionary.

    Args:
    ----
        obj (BaseModel): The Pydantic model instance to serialize.

    Returns:
    -------
        dict: The serialized dictionary representation of the model.

    Raises:
    ------
        TypeError: If the object is not a Pydantic BaseModel instance.

    """
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    raise TypeError(f"Type {type(obj)} not serializable")


def convert_output_parameters(username: str, outputs: dict[str, any]) -> dict[str, dict]:  # type: ignore # noqa: PGH003
    """Convert the output parameters to the Parameter class."""
    converted = {}
    for param_name, output in outputs.items():
        param = ParameterModel(
            username=username, name=param_name, unit=output.unit, description=output.description
        )  # type: ignore # noqa: PGH003
        converted[param_name] = param.model_dump()
    return converted


@task
def update_active_output_parameters(username: str, backend: str) -> list[ParameterModel]:
    """Update the active output parameters in the input file.

    Args:
    ----
        file_path: The path to the input file.

    """
    task_cls = BaseTask.registry.get(backend)
    all_outputs = {cls.name: cls.output_parameters for cls in task_cls.values()}
    converted_outputs = {
        task_name: convert_output_parameters(username=username, outputs=outputs)
        for task_name, outputs in all_outputs.items()
    }

    unique_parameter_names = {
        param_name for outputs in converted_outputs.values() for param_name in outputs
    }
    return [
        ParameterModel(
            username=username,
            name=name,
            unit=converted_outputs[
                next(task for task in converted_outputs if name in converted_outputs[task])
            ][name]["unit"],
            description=converted_outputs[
                next(task for task in converted_outputs if name in converted_outputs[task])
            ][name]["description"],
        )
        for name in unique_parameter_names
    ]


@task
def update_active_tasks(username: str, backend: str) -> list[TaskModel]:
    """Update the active tasks in the registry and return a list of TaskModel instances."""
    task_cls = BaseTask.registry.get(backend)
    return [
        TaskModel(
            username=username,
            backend=backend,
            name=cls.name,
            description=cls.__doc__,
            task_type=cls.task_type,
            input_parameters={
                name: param.model_dump() for name, param in cls.input_parameters.items()
            },
            output_parameters={
                name: param.model_dump() for name, param in cls.output_parameters.items()
            },
        )
        for cls in task_cls.values()
    ]
