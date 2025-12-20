"""In-memory implementation of ChipHistoryRepository for testing.

This module provides a mock implementation that stores chip history in memory,
useful for unit testing without requiring a MongoDB instance.
"""


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
