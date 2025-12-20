"""In-memory implementations of repositories for testing.

This module provides mock implementations that store data in memory,
useful for unit testing without requiring a MongoDB instance.

These implementations follow the same protocols as the MongoDB implementations
but use in-memory dictionaries for storage.
"""

from collections.abc import Callable
from typing import Any

from qdash.datamodel.execution import (
    CalibDataModel,
    ExecutionModel,
)


class InMemoryExecutionRepository:
    """In-memory implementation of ExecutionRepository for testing.

    This implementation stores executions in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryExecutionRepository()
        >>> model = ExecutionModel(execution_id="exec-001", ...)
        >>> repo.save(model)
        >>> found = repo.find_by_id("exec-001")
        >>> assert found.execution_id == "exec-001"

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._executions: dict[str, ExecutionModel] = {}

    def save(self, execution: ExecutionModel) -> None:
        """Save execution state to in-memory storage.

        Parameters
        ----------
        execution : ExecutionModel
            The execution model to save

        """
        self._executions[execution.execution_id] = execution

    def find_by_id(self, execution_id: str) -> ExecutionModel | None:
        """Find execution by ID.

        Parameters
        ----------
        execution_id : str
            The execution identifier

        Returns
        -------
        ExecutionModel | None
            The execution model if found, None otherwise

        """
        return self._executions.get(execution_id)

    def update_with_optimistic_lock(
        self,
        execution_id: str,
        update_func: Callable[[ExecutionModel], None],
        initial_model: ExecutionModel | None = None,
    ) -> ExecutionModel:
        """Update execution with optimistic locking simulation.

        In-memory implementation doesn't need real locking but maintains
        the same interface for testing.

        Parameters
        ----------
        execution_id : str
            The execution identifier
        update_func : callable
            Function that takes ExecutionModel and modifies it in place
        initial_model : ExecutionModel | None
            Initial model to use if document doesn't exist

        Returns
        -------
        ExecutionModel
            The updated execution model

        Raises
        ------
        ValueError
            If execution not found and no initial model provided

        """
        model = self._executions.get(execution_id)
        if model is None:
            if initial_model is not None:
                model = initial_model
                self._executions[execution_id] = model
            else:
                raise ValueError(f"Execution {execution_id} not found")

        update_func(model)
        return model

    def clear(self) -> None:
        """Clear all stored executions (useful for test setup/teardown)."""
        self._executions.clear()


class InMemoryExecutionCounterRepository:
    """In-memory implementation of ExecutionCounterRepository for testing.

    This implementation stores counters in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryExecutionCounterRepository()
        >>> index1 = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")
        >>> assert index1 == 0
        >>> index2 = repo.get_next_index("20240101", "alice", "chip_1", "proj-1")
        >>> assert index2 == 1

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._counters: dict[str, int] = {}

    def get_next_index(
        self,
        date: str,
        username: str,
        chip_id: str,
        project_id: str | None,
    ) -> int:
        """Get the next execution index atomically.

        Parameters
        ----------
        date : str
            The date string (e.g., "20240115")
        username : str
            The username
        chip_id : str
            The chip identifier
        project_id : str
            The project identifier

        Returns
        -------
        int
            The next index (0 on first call, then 1, 2, 3...)

        """
        key = f"{date}:{username}:{chip_id}:{project_id}"
        current = self._counters.get(key, -1)
        next_index = current + 1
        self._counters[key] = next_index
        return next_index

    def clear(self) -> None:
        """Clear all stored counters (useful for test setup/teardown)."""
        self._counters.clear()


class InMemoryExecutionLockRepository:
    """In-memory implementation of ExecutionLockRepository for testing.

    This implementation stores lock states in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryExecutionLockRepository()
        >>> assert not repo.is_locked("proj-1")
        >>> repo.lock("proj-1")
        >>> assert repo.is_locked("proj-1")
        >>> repo.unlock("proj-1")
        >>> assert not repo.is_locked("proj-1")

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._locks: dict[str, bool] = {}

    def is_locked(self, project_id: str) -> bool:
        """Check if the project is currently locked.

        Parameters
        ----------
        project_id : str
            The project identifier

        Returns
        -------
        bool
            True if locked, False otherwise

        """
        return self._locks.get(project_id, False)

    def lock(self, project_id: str) -> None:
        """Acquire the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier

        """
        self._locks[project_id] = True

    def unlock(self, project_id: str) -> None:
        """Release the execution lock.

        Parameters
        ----------
        project_id : str
            The project identifier

        """
        self._locks[project_id] = False

    def clear(self) -> None:
        """Clear all locks (useful for test setup/teardown)."""
        self._locks.clear()


class InMemoryUserRepository:
    """In-memory implementation of UserRepository for testing.

    This implementation stores user data in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryUserRepository()
        >>> repo.add_user("alice", default_project_id="proj-1")
        >>> assert repo.get_default_project_id("alice") == "proj-1"

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._users: dict[str, dict[str, Any]] = {}

    def get_default_project_id(self, username: str) -> str | None:
        """Get the user's default project ID.

        Parameters
        ----------
        username : str
            The username to look up

        Returns
        -------
        str | None
            The default project ID, or None if not set or user not found

        """
        user = self._users.get(username)
        if user is None:
            return None
        return user.get("default_project_id")

    def add_user(
        self,
        username: str,
        default_project_id: str | None = None,
    ) -> None:
        """Add a user to the repository (test helper).

        Parameters
        ----------
        username : str
            The username
        default_project_id : str | None
            The user's default project ID

        """
        self._users[username] = {"default_project_id": default_project_id}

    def clear(self) -> None:
        """Clear all stored users (useful for test setup/teardown)."""
        self._users.clear()


class InMemoryTaskRepository:
    """In-memory implementation of TaskRepository for testing.

    This implementation stores task definitions in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryTaskRepository()
        >>> repo.add_tasks("alice", ["CheckFreq", "CheckRabi"])
        >>> names = repo.get_task_names("alice")
        >>> assert "CheckFreq" in names

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._tasks: dict[str, list[str]] = {}

    def get_task_names(self, username: str) -> list[str]:
        """Get all task names available for a user.

        Parameters
        ----------
        username : str
            The username to look up tasks for

        Returns
        -------
        list[str]
            List of available task names

        """
        return self._tasks.get(username, [])

    def add_tasks(self, username: str, task_names: list[str]) -> None:
        """Add tasks for a user (test helper).

        Parameters
        ----------
        username : str
            The username
        task_names : list[str]
            List of task names to add

        """
        if username not in self._tasks:
            self._tasks[username] = []
        self._tasks[username].extend(task_names)

    def clear(self) -> None:
        """Clear all stored tasks (useful for test setup/teardown)."""
        self._tasks.clear()


class InMemoryChipRepository:
    """In-memory implementation of ChipRepository for testing.

    This implementation stores chip data in a dictionary, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> from qdash.datamodel.chip import ChipModel
        >>> repo = InMemoryChipRepository()
        >>> chip = ChipModel(chip_id="chip_1", ...)
        >>> repo.add_chip("alice", chip)
        >>> found = repo.get_current_chip("alice")
        >>> assert found.chip_id == "chip_1"

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        from qdash.datamodel.chip import ChipModel

        self._chips: dict[str, ChipModel] = {}  # username -> chip
        self._chips_by_id: dict[str, ChipModel] = {}  # (username, chip_id) -> chip

    def get_current_chip(self, username: str) -> Any | None:
        """Get the most recently installed chip for a user.

        Parameters
        ----------
        username : str
            The username to look up the chip

        Returns
        -------
        ChipModel | None
            The current chip or None if not found

        """
        return self._chips.get(username)

    def get_chip_by_id(self, username: str, chip_id: str) -> Any | None:
        """Get a specific chip by chip_id and username.

        Parameters
        ----------
        username : str
            The username of the chip owner
        chip_id : str
            The specific chip ID to retrieve

        Returns
        -------
        ChipModel | None
            The chip if found, None otherwise

        """
        key = f"{username}:{chip_id}"
        return self._chips_by_id.get(key)

    def update_chip_data(
        self,
        chip_id: str,
        calib_data: CalibDataModel,
        username: str,
    ) -> None:
        """Update chip calibration data.

        Parameters
        ----------
        chip_id : str
            The chip identifier
        calib_data : CalibDataModel
            The calibration data to merge
        username : str
            The user performing the update

        """
        key = f"{username}:{chip_id}"
        chip = self._chips_by_id.get(key)
        if chip is None:
            return

        # Merge qubit data
        for qid, data in calib_data.qubit.items():
            if qid not in chip.qubits:
                continue
            for param_name, param_value in data.items():
                if hasattr(chip.qubits[qid], "data"):
                    chip.qubits[qid].data[param_name] = param_value

        # Merge coupling data
        for cid, data in calib_data.coupling.items():
            if cid not in chip.couplings:
                continue
            for param_name, param_value in data.items():
                if hasattr(chip.couplings[cid], "data"):
                    chip.couplings[cid].data[param_name] = param_value

    def add_chip(self, username: str, chip: Any) -> None:
        """Add a chip for a user (test helper).

        Parameters
        ----------
        username : str
            The username
        chip : ChipModel
            The chip to add

        """
        self._chips[username] = chip
        key = f"{username}:{chip.chip_id}"
        self._chips_by_id[key] = chip

    def clear(self) -> None:
        """Clear all stored chips (useful for test setup/teardown)."""
        self._chips.clear()
        self._chips_by_id.clear()


class InMemoryTaskResultHistoryRepository:
    """In-memory implementation of TaskResultHistoryRepository for testing.

    This implementation stores task results in a list, making it suitable
    for unit tests that don't require a real database.

    Example
    -------
        >>> from qdash.datamodel.task import BaseTaskResultModel
        >>> repo = InMemoryTaskResultHistoryRepository()
        >>> repo.save(task_result, execution_model)
        >>> assert len(repo.get_all()) == 1

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        from qdash.datamodel.task import BaseTaskResultModel

        self._history: list[tuple[BaseTaskResultModel, ExecutionModel]] = []

    def save(self, task: Any, execution_model: ExecutionModel) -> None:
        """Save a task result to the history.

        Parameters
        ----------
        task : BaseTaskResultModel
            The task result to save
        execution_model : ExecutionModel
            The parent execution context

        """
        self._history.append((task, execution_model))

    def get_all(self) -> list[tuple[Any, ExecutionModel]]:
        """Get all stored task results (test helper).

        Returns
        -------
        list[tuple[BaseTaskResultModel, ExecutionModel]]
            All stored task results with their execution contexts

        """
        return list(self._history)

    def clear(self) -> None:
        """Clear all stored history (useful for test setup/teardown)."""
        self._history.clear()


class InMemoryChipHistoryRepository:
    """In-memory implementation of ChipHistoryRepository for testing.

    This implementation stores chip history snapshots in a list, making it
    suitable for unit tests that don't require a real database.

    Example
    -------
        >>> repo = InMemoryChipHistoryRepository()
        >>> repo.create_history("alice", "chip_1")
        >>> assert len(repo.get_all()) == 1

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._history: list[dict[str, str | None]] = []

    def create_history(self, username: str, chip_id: str | None = None) -> None:
        """Create a chip history snapshot.

        Parameters
        ----------
        username : str
            The username to look up the chip
        chip_id : str, optional
            The specific chip ID to create history for.
            If None, uses the current (most recently installed) chip.

        """
        self._history.append({"username": username, "chip_id": chip_id})

    def get_all(self) -> list[dict[str, str | None]]:
        """Get all stored history snapshots (test helper).

        Returns
        -------
        list[dict[str, str | None]]
            All stored history snapshots

        """
        return list(self._history)

    def clear(self) -> None:
        """Clear all stored history (useful for test setup/teardown)."""
        self._history.clear()


class InMemoryQubitCalibrationRepository:
    """In-memory implementation of QubitCalibrationRepository for testing.

    This implementation stores qubit calibration data in a dictionary,
    making it suitable for unit tests that don't require a real database.

    Example
    -------
        >>> from qdash.datamodel.qubit import QubitModel
        >>> repo = InMemoryQubitCalibrationRepository()
        >>> qubit = QubitModel(qid="0", chip_id="chip_1", ...)
        >>> repo.add_qubit("alice", qubit)
        >>> found = repo.find_one(username="alice", qid="0", chip_id="chip_1")
        >>> assert found is not None

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        from qdash.datamodel.qubit import QubitModel

        self._qubits: dict[str, QubitModel] = {}  # key -> qubit

    def _make_key(self, username: str, qid: str, chip_id: str) -> str:
        """Create storage key from identifiers."""
        return f"{username}:{chip_id}:{qid}"

    def update_calib_data(
        self,
        *,
        username: str,
        qid: str,
        chip_id: str,
        output_parameters: dict[str, Any],
        project_id: str | None,
    ) -> Any:
        """Update qubit calibration data with new measurement results.

        Parameters
        ----------
        username : str
            The username performing the update
        qid : str
            The qubit identifier (e.g., "0", "1")
        chip_id : str
            The chip identifier
        output_parameters : dict[str, Any]
            The new calibration parameters to merge
        project_id : str | None
            The project identifier

        Returns
        -------
        QubitModel
            The updated qubit model

        Raises
        ------
        ValueError
            If the qubit is not found

        """
        from qdash.datamodel.qubit import QubitModel

        key = self._make_key(username, qid, chip_id)
        qubit = self._qubits.get(key)

        if qubit is None:
            # Create new qubit if not exists
            qubit = QubitModel(
                project_id=project_id,
                username=username,
                qid=qid,
                status="",
                chip_id=chip_id,
                data={},
                best_data={},
                node_info=None,
            )
            self._qubits[key] = qubit

        # Merge parameters into data
        for param_name, param_value in output_parameters.items():
            qubit.data[param_name] = param_value

        return qubit

    def find_one(
        self,
        *,
        username: str,
        qid: str,
        chip_id: str,
    ) -> Any | None:
        """Find a qubit by identifiers.

        Parameters
        ----------
        username : str
            The username
        qid : str
            The qubit identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        QubitModel | None
            The qubit model if found, None otherwise

        """
        key = self._make_key(username, qid, chip_id)
        return self._qubits.get(key)

    def add_qubit(self, username: str, qubit: Any) -> None:
        """Add a qubit for testing (test helper).

        Parameters
        ----------
        username : str
            The username
        qubit : QubitModel
            The qubit to add

        """
        key = self._make_key(username, qubit.qid, qubit.chip_id)
        self._qubits[key] = qubit

    def clear(self) -> None:
        """Clear all stored qubits (useful for test setup/teardown)."""
        self._qubits.clear()


class InMemoryCouplingCalibrationRepository:
    """In-memory implementation of CouplingCalibrationRepository for testing.

    This implementation stores coupling calibration data in a dictionary,
    making it suitable for unit tests that don't require a real database.

    Example
    -------
        >>> from qdash.datamodel.coupling import CouplingModel
        >>> repo = InMemoryCouplingCalibrationRepository()
        >>> coupling = CouplingModel(qid="0-1", chip_id="chip_1", ...)
        >>> repo.add_coupling("alice", coupling)
        >>> found = repo.find_one(username="alice", qid="0-1", chip_id="chip_1")
        >>> assert found is not None

    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        from qdash.datamodel.coupling import CouplingModel

        self._couplings: dict[str, CouplingModel] = {}  # key -> coupling

    def _make_key(self, username: str, qid: str, chip_id: str) -> str:
        """Create storage key from identifiers."""
        return f"{username}:{chip_id}:{qid}"

    def update_calib_data(
        self,
        *,
        username: str,
        qid: str,
        chip_id: str,
        output_parameters: dict[str, Any],
        project_id: str | None,
    ) -> Any:
        """Update coupling calibration data with new measurement results.

        Parameters
        ----------
        username : str
            The username performing the update
        qid : str
            The coupling identifier (e.g., "0-1")
        chip_id : str
            The chip identifier
        output_parameters : dict[str, Any]
            The new calibration parameters to merge
        project_id : str | None
            The project identifier

        Returns
        -------
        CouplingModel
            The updated coupling model

        Raises
        ------
        ValueError
            If the coupling is not found

        """
        from qdash.datamodel.coupling import CouplingModel

        key = self._make_key(username, qid, chip_id)
        coupling = self._couplings.get(key)

        if coupling is None:
            # Create new coupling if not exists
            coupling = CouplingModel(
                project_id=project_id,
                username=username,
                qid=qid,
                status="",
                chip_id=chip_id,
                data={},
                best_data={},
                edge_info=None,
            )
            self._couplings[key] = coupling

        # Merge parameters into data
        for param_name, param_value in output_parameters.items():
            coupling.data[param_name] = param_value

        return coupling

    def find_one(
        self,
        *,
        username: str,
        qid: str,
        chip_id: str,
    ) -> Any | None:
        """Find a coupling by identifiers.

        Parameters
        ----------
        username : str
            The username
        qid : str
            The coupling identifier
        chip_id : str
            The chip identifier

        Returns
        -------
        CouplingModel | None
            The coupling model if found, None otherwise

        """
        key = self._make_key(username, qid, chip_id)
        return self._couplings.get(key)

    def add_coupling(self, username: str, coupling: Any) -> None:
        """Add a coupling for testing (test helper).

        Parameters
        ----------
        username : str
            The username
        coupling : CouplingModel
            The coupling to add

        """
        key = self._make_key(username, coupling.qid, coupling.chip_id)
        self._couplings[key] = coupling

    def clear(self) -> None:
        """Clear all stored couplings (useful for test setup/teardown)."""
        self._couplings.clear()
