from enum import Enum


class SystemRole(str, Enum):
    """System-level role for a user.

    ADMIN: Full system access, can manage all users and projects.
    USER: Regular user.
    """

    ADMIN = "admin"
    USER = "user"
