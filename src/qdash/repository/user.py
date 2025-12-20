"""MongoDB implementation of UserRepository.

This module provides the concrete MongoDB implementation for user
data access operations.
"""

import logging
from typing import Any

from qdash.dbmodel.user import UserDocument

logger = logging.getLogger(__name__)


class MongoUserRepository:
    """MongoDB implementation of UserRepository.

    This class delegates to UserDocument for user data access.

    Example
    -------
        >>> repo = MongoUserRepository()
        >>> project_id = repo.get_default_project_id(username="alice")

    """

    def find_one(self, query: dict[str, Any]) -> UserDocument | None:
        """Find a single user document by query.

        Parameters
        ----------
        query : dict[str, Any]
            MongoDB query dict

        Returns
        -------
        UserDocument | None
            The user document if found, None otherwise

        """
        return UserDocument.find_one(query).run()

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
        user = self.find_one({"username": username})
        if user is None:
            return None
        # default_project_id is str | None
        default_project_id: str | None = user.default_project_id
        return default_project_id

    def find_by_username(self, username: str) -> UserDocument | None:
        """Find a user by username.

        Parameters
        ----------
        username : str
            The username to look up

        Returns
        -------
        UserDocument | None
            The user document if found, None otherwise

        """
        return self.find_one({"username": username})

    def insert(self, user: UserDocument) -> None:
        """Insert a new user document.

        Parameters
        ----------
        user : UserDocument
            The user document to insert

        """
        user.insert()

    def save(self, user: UserDocument) -> None:
        """Save (update) an existing user document.

        Parameters
        ----------
        user : UserDocument
            The user document to save

        """
        user.save()
