import logging
from typing import ClassVar

from bunnet import Document
from datamodel.task import TaskModel
from pydantic import ConfigDict, Field
from pymongo import ASCENDING, IndexModel

logger = logging.getLogger(__name__)


class TaskDocument(Document):
    """Document model for a task in the database.

    Attributes
    ----------
        name (str): The name of the task. e.g. "CheckT1" ,"CheckT2Echo" ".
        description (str): Detailed description of the task.
        task_type (str): The type of the task. e.g. "global", "qubit", "coupling".

    """

    name: str = Field(..., description="The name of the task")
    description: str = Field(..., description="Detailed description of the task")
    task_type: str = Field(..., description="The type of the task")

    model_config = ConfigDict(
        from_attributes=True,
    )

    class Settings:
        """Database settings for ParameterDocument."""

        name = "task"
        indexes: ClassVar = [IndexModel([("name", ASCENDING)], unique=True)]

    @classmethod
    def from_task_model(cls, model: TaskModel) -> "TaskDocument":
        """Create a ParameterDocument from a ParameterModel.

        Parameters
        ----------
        model : ParameterModel
            The parameter model to convert.

        Returns
        -------
        ParameterDocument
            The converted parameter document.

        """
        return cls(
            name=model.name,
            task_type=model.task_type,
            description=model.description,
        )

    @classmethod
    def insert_tasks(cls, tasks: list[TaskModel]) -> list["TaskDocument"]:
        inserted_documents = []
        for task in tasks:
            logger.debug(f"Inserting task: {task}")
            doc = cls.find_one(cls.name == task.name).run()
            if doc is None:
                logger.debug(f"Task {task.name} not found. Inserting new task.")
                doc = cls.from_task_model(task)
                doc.save()
                logger.debug(f"Task {task.name} inserted.")
            else:
                logger.debug(f"Task {task.name} found. Updating task.")
                doc.task_type = task.task_type
                doc.description = task.description
                doc.save()
                logger.debug(f"Task {task.name} updated with new values.")
            inserted_documents.append(doc)
        return inserted_documents
