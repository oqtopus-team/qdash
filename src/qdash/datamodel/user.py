from enum import Enum
from uuid import uuid4


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
