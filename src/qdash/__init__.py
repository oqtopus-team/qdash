"""QDash: Quantum calibration dashboard and Python client."""

__version__ = "0.1.0"

# Import client for easy access
try:
    from .client import AuthenticatedClient, Client

    __all__ = ["Client", "AuthenticatedClient", "__version__"]
except ImportError:
    # Client not generated yet
    __all__ = ["__version__"]
