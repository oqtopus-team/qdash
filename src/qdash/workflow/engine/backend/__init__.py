"""Backend Abstraction Layer - Hardware interface abstraction.

This module provides an abstraction layer for different calibration backends,
allowing the same workflow code to run on real hardware or simulation.

Components
----------
BaseBackend
    Abstract base class defining the backend interface.
    All backends must implement:
    - connect(): Initialize hardware connection
    - get_instance(): Return the experiment session
    - save_note(): Save calibration note to database
    - update_note(): Update existing calibration note

FakeBackend
    Simulation backend for testing without real hardware.
    Returns mock results for all measurements.

QubexBackend
    Real hardware backend using the qubex library.
    Not exported by default to avoid import errors when qubex is not installed.
    Import directly: ``from qdash.workflow.engine.backend.qubex import QubexBackend``

create_backend
    Factory function to create backends by name.

Backend Interface
-----------------
::

    class MyBackend(BaseBackend):
        name = "my_backend"

        def connect(self) -> None:
            # Initialize hardware connection
            pass

        def get_instance(self) -> Any:
            # Return experiment session
            return self._session

        def save_note(...) -> None:
            # Save calibration note
            pass

        def update_note(...) -> None:
            # Update calibration note
            pass

Usage Example
-------------
>>> from qdash.workflow.engine.backend import create_backend
>>> backend = create_backend(
...     backend="qubex",  # or "fake" for testing
...     config={
...         "username": "alice",
...         "chip_id": "64Qv3",
...         "qids": ["0", "1"],
...         "note_path": "/path/to/note.json",
...     },
... )
>>> backend.connect()
>>> session = backend.get_instance()

Adding a New Backend
--------------------
1. Create a new file ``engine/backend/your_backend.py``
2. Implement the ``BaseBackend`` interface
3. Register in ``engine/backend/factory.py``
"""

from qdash.workflow.engine.backend.base import BaseBackend
from qdash.workflow.engine.backend.factory import create_backend
from qdash.workflow.engine.backend.fake import FakeBackend

__all__ = [
    "BaseBackend",
    "FakeBackend",
    "create_backend",
]

# Note: QubexBackend is not exported here to avoid import errors when qubex is not installed.
# Import it directly: from qdash.workflow.engine.backend.qubex import QubexBackend
