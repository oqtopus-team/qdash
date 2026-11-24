"""The project's chips: list them and read one chip's metadata.

These operations read the server's ``/chips`` routes and change nothing. Calibration on a
chip goes through :meth:`QDash.chip`, which sends no request of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qdash.sdk._http import api_errors, read_options

if TYPE_CHECKING:
    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.types.chip_response import ChipResponse


class Chips:
    """The chips of the session's project, reached as ``QDash.chips``."""

    def __init__(self, api: QDashApi, config: QDashConfig) -> None:
        self._api = api
        self._config = config

    def list(self) -> list[ChipResponse]:
        """Metadata of every chip in the session's project."""
        with api_errors():
            response = self._api.chip.list_chips(request_options=read_options(self._config))
        return list(response.chips)

    def get(self, chip_id: str) -> ChipResponse:
        """Metadata of ``chip_id``; raises ``QDashNotFoundError`` when there is none.

        Returns the chip's metadata and counts, not its qubits or couplings; those are on
        ``QDash.api.chip``. To calibrate the chip, use ``QDash.chip(chip_id)``.
        """
        if not isinstance(chip_id, str) or not chip_id:
            raise ValueError("chip_id must be a non-empty string")
        with api_errors():
            return self._api.chip.get_chip(chip_id, request_options=read_options(self._config))
