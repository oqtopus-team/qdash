from qdash.neodbmodel.chip import ChipDocument
from qdash.neodbmodel.coupling import CouplingDocument
from qdash.neodbmodel.execution_counter import ExecutionCounterDocument
from qdash.neodbmodel.execution_history import ExecutionHistoryDocument
from qdash.neodbmodel.execution_lock import ExecutionLockDocument
from qdash.neodbmodel.menu import MenuDocument
from qdash.neodbmodel.parameter import ParameterDocument
from qdash.neodbmodel.qubit import QubitDocument
from qdash.neodbmodel.task import TaskDocument
from qdash.neodbmodel.task_result_history import TaskResultHistoryDocument
from qdash.neodbmodel.user import UserDocument


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
    ]
