from qdash.dbmodel.chip import ChipDocument
from qdash.dbmodel.coupling import CouplingDocument
from qdash.dbmodel.execution_counter import ExecutionCounterDocument
from qdash.dbmodel.execution_history import ExecutionHistoryDocument
from qdash.dbmodel.execution_lock import ExecutionLockDocument
from qdash.dbmodel.menu import MenuDocument
from qdash.dbmodel.parameter import ParameterDocument
from qdash.dbmodel.qubit import QubitDocument
from qdash.dbmodel.tag import TagDocument
from qdash.dbmodel.task import TaskDocument
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.dbmodel.user import UserDocument


def document_models() -> list[str]:
    """Initialize the repository and create initial data if needed."""
    return [
        ExecutionHistoryDocument,
        TaskResultHistoryDocument,
        QubitDocument,
        ChipDocument,
        ParameterDocument,
        TaskDocument,
        CouplingDocument,
        UserDocument,
        MenuDocument,
        ExecutionCounterDocument,
        ExecutionLockDocument,
        TagDocument,
    ]
