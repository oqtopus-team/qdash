"""In-memory implementation of UserRepository for testing.

This module provides a mock implementation that stores user data in memory,
useful for unit testing without requiring a MongoDB instance.
"""

from typing import Any


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
