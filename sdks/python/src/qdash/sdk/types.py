"""Request and response types of the QDash API, generated from its OpenAPI document.

Every name of ``qdash.sdk._generated.types`` is available here, imported on first use, e.g.
``from qdash.sdk.types import ExecutionResponseDetail``. Response models accept fields a newer
server adds. The strict models the SDK builds request bodies from are in
:mod:`qdash.sdk.pipeline` and :mod:`qdash.sdk.dashboard`.
"""

from typing import TYPE_CHECKING, Any

from qdash.sdk._generated import types as _types

if TYPE_CHECKING:
    from qdash.sdk._generated.types import *  # noqa: F403

__all__ = list(_types.__all__)


def __getattr__(name: str) -> Any:
    return getattr(_types, name)


def __dir__() -> list[str]:
    return __all__
