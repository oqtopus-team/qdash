"""QDash SDK: define calibration pipelines in Python and run them through the QDash API.

The SDK is part of the ``qdash-client`` distribution and reuses its configuration,
authentication, transport and errors. Pipeline definitions live in :mod:`qdash.sdk.pipeline`.
"""

from qdash.client.services.errors import (
    QDashApiError,
    QDashAuthError,
    QDashConfigError,
    QDashNotFoundError,
    QDashTransportError,
    QDashValidationError,
)
from qdash.sdk._pipelines import PipelineRun, Pipelines
from qdash.sdk._session import QDash

__all__ = [
    "PipelineRun",
    "Pipelines",
    "QDash",
    "QDashApiError",
    "QDashAuthError",
    "QDashConfigError",
    "QDashNotFoundError",
    "QDashTransportError",
    "QDashValidationError",
]
