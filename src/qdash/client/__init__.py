"""A client library for accessing QDash API"""

__version__ = "0.1.0"

from .client import AuthenticatedClient, Client

__all__ = (
    "AuthenticatedClient",
    "Client",
)
