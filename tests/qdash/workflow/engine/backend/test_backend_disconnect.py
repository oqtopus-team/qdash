"""Backend disconnect releases an existing Experiment without creating a new one."""

from unittest.mock import MagicMock

import pytest

from qdash.workflow.engine.backend.fake import FakeBackend
from qdash.workflow.engine.backend.qubex import QubexBackend


@pytest.mark.parametrize("backend_type", [FakeBackend, QubexBackend])
def test_disconnect_is_safe_without_an_experiment(
    backend_type: type[FakeBackend | QubexBackend],
) -> None:
    backend = backend_type({})

    backend.disconnect()

    assert backend._exp is None


@pytest.mark.parametrize("backend_type", [FakeBackend, QubexBackend])
def test_disconnect_releases_experiment_once(
    backend_type: type[FakeBackend | QubexBackend],
) -> None:
    backend = backend_type({})
    experiment = MagicMock()
    backend._exp = experiment

    backend.disconnect()
    backend.disconnect()

    experiment.disconnect.assert_called_once_with()
    assert backend._exp is None
