"""The installed ``qdash-sdk`` version, read once from the package metadata."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version


def _installed_version() -> str:
    try:
        return _distribution_version("qdash-sdk")
    except PackageNotFoundError:
        # Imported from a source tree without installed distribution metadata.
        return "unknown"


__version__: str = _installed_version()


def version() -> str:
    """The installed ``qdash-sdk`` version, or ``"unknown"`` without package metadata.

    The value is read from the installed distribution when the SDK is imported; calling
    this function needs no configuration, authentication or network access.
    """
    return __version__
