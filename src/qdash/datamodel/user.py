import re
from enum import Enum
from typing import Annotated
from uuid import uuid4

from pydantic import StringConstraints

USERNAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,62}[a-z0-9]$"
USERNAME_PATTERN_DESCRIPTION = (
    "Username must be 3-64 characters, lowercase letters, numbers, dots, "
    "underscores, or hyphens, and start and end with a letter or number."
)
Username = Annotated[str, StringConstraints(pattern=USERNAME_PATTERN)]
_USERNAME_RE = re.compile(USERNAME_PATTERN)


class SystemRole(str, Enum):
    """System-level role for a user.

    ADMIN: Full system access, can manage all users and projects.
    USER: Regular user.
    """

    ADMIN = "admin"
    USER = "user"


def generate_user_id() -> str:
    """Generate an opaque internal user identifier."""
    return f"usr_{uuid4().hex}"


def is_valid_username(username: str) -> bool:
    """Return whether username matches the canonical username format."""
    return bool(_USERNAME_RE.fullmatch(username))
