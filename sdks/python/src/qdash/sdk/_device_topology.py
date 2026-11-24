"""The device topology a device gateway publishes, built from the latest calibration.

``QDash.device_topology.create(...)`` asks the server for the topology of the qubits and
couplings that pass a filter, and returns a :class:`DeviceTopology` snapshot of the response.
:meth:`DeviceTopology.save` writes it as JSON and :meth:`DeviceTopology.plot` asks the server
to draw it as a PNG. Both server routes are POST computations that store nothing; the SDK sends
each of them once, as it does every POST, and writes files only when ``save`` is called.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

import pydantic

from qdash.sdk._generated.types.condition import Condition
from qdash.sdk._generated.types.fidelity_condition import FidelityCondition
from qdash.sdk._http import api_errors
from qdash.sdk._results import check_save_target, write_file
from qdash.sdk._runs import _file_content
from qdash.sdk.errors import QDashTransportError

if TYPE_CHECKING:
    import datetime as dt
    import os
    from pathlib import Path

    from qdash.sdk._config import QDashConfig
    from qdash.sdk._generated.client import QDashApi
    from qdash.sdk._generated.core.request_options import RequestOptions
    from qdash.sdk._generated.types.coupling import Coupling
    from qdash.sdk._generated.types.device import Device
    from qdash.sdk._generated.types.qubit import Qubit

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_FIDELITY_FIELDS = ("coupling_fidelity", "qubit_fidelity", "readout_fidelity")


def _known_keys(model: type[pydantic.BaseModel]) -> set[str]:
    keys: set[str] = set()
    for name, info in model.model_fields.items():
        keys.add(name)
        if info.alias:
            keys.add(info.alias)
    return keys


def _mapping(value: object, what: str) -> dict[str, Any]:
    if isinstance(value, pydantic.BaseModel):
        dumped: dict[str, Any] = value.model_dump(by_alias=True, exclude_unset=True)
        return dumped
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"{what} must be a mapping or a {Condition.__name__}-like model")


def _reject_unknown(data: Mapping[str, Any], model: type[pydantic.BaseModel], what: str) -> None:
    unknown = sorted(str(key) for key in data if key not in _known_keys(model))
    if unknown:
        raise ValueError(
            f"{what} has unknown fields {unknown}; the SDK does not send fields it does not "
            "know, so a misspelled filter cannot be ignored silently"
        )


def _condition(value: Condition | Mapping[str, Any]) -> Condition:
    """``value`` checked against the API's condition schema, rejecting unknown fields.

    The generated models accept unknown fields, and the server ignores unknown fields inside a
    fidelity filter, so a misspelled key would otherwise change the topology without an error.
    """
    data = _mapping(value, "condition")
    _reject_unknown(data, Condition, "condition")
    for field in _FIDELITY_FIELDS:
        if field in data and data[field] is not None:
            data[field] = _mapping(data[field], f"condition.{field}")
            _reject_unknown(data[field], FidelityCondition, f"condition.{field}")
    try:
        return Condition.model_validate(data)
    except pydantic.ValidationError as error:
        raise ValueError(f"invalid condition: {error}") from None


def _labels(value: Sequence[str], what: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{what} must be a list of strings, e.g. ['0', '1']")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{what} must contain strings, e.g. ['0', '1']")
    return list(value)


def _text(value: str, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{what} must be a non-empty string")
    return value


class DeviceTopologyPlot:
    """A PNG drawing of a device topology, held in memory as the server returned it.

    Reading or saving it sends no request. In a notebook, the plot displays itself as the
    value of a cell; :meth:`show` displays it explicitly.
    """

    def __init__(self, content: bytes) -> None:
        self._content = content

    def __repr__(self) -> str:
        return f"{type(self).__name__}(png, {len(self._content)} bytes)"

    def read(self) -> bytes:
        """The PNG bytes."""
        return self._content

    def save(self, path: str | os.PathLike[str], *, overwrite: bool = False) -> Path:
        """Write the PNG to ``path``, a file name the caller chooses, and return the path.

        An existing file raises ``FileExistsError`` unless ``overwrite`` is true; a directory
        raises ``IsADirectoryError``. Missing parent directories are not created.
        """
        target = check_save_target(path, overwrite=overwrite)
        return write_file(target, self._content, overwrite=overwrite)

    def show(self) -> None:
        """Display the PNG in the running notebook (needs IPython)."""
        try:
            from IPython.display import Image, display
        except ImportError:
            raise ImportError(
                "DeviceTopologyPlot.show() needs IPython, which notebooks provide; install "
                "ipython, or use plot.read() or plot.save(path) instead"
            ) from None
        display(Image(data=self._content, format="png"))

    def _repr_png_(self) -> bytes:
        return self._content


class DeviceTopology:
    """A device topology as the server computed it; reading its fields sends no request.

    ``detail`` is the generated ``Device`` model. :meth:`to_dict` and :meth:`save` use the
    API's field names, such as ``prob_meas1_prep0``, so the JSON matches what a device gateway
    reads, and keep fields a newer server adds.
    """

    def __init__(self, api: QDashApi, detail: Device) -> None:
        self._api = api
        self.detail = detail

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(device_id={self.device_id!r}, qubits={len(self.qubits)}, "
            f"couplings={len(self.couplings)}, calibrated_at={self.calibrated_at!r})"
        )

    @property
    def name(self) -> str:
        return self.detail.name

    @property
    def device_id(self) -> str:
        """The label given to :meth:`DeviceTopologies.create`; it does not select a chip."""
        return self.detail.device_id

    @property
    def qubits(self) -> list[Qubit]:
        """The qubits that passed the filter, numbered from 0 in physical-ID order."""
        return list(self.detail.qubits)

    @property
    def couplings(self) -> list[Coupling]:
        return list(self.detail.couplings)

    @property
    def calibrated_at(self) -> dt.datetime | str:
        return self.detail.calibrated_at

    def to_dict(self) -> dict[str, Any]:
        """The topology as JSON-ready data with the API's field names."""
        data: dict[str, Any] = self.detail.model_dump(by_alias=True, mode="json")
        return data

    def save(self, path: str | os.PathLike[str], *, overwrite: bool = False) -> Path:
        """Write the topology as indented JSON to ``path`` and return the path.

        An existing file raises ``FileExistsError`` unless ``overwrite`` is true; a directory
        raises ``IsADirectoryError``. Missing parent directories are not created.
        """
        target = check_save_target(path, overwrite=overwrite)
        text = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        return write_file(target, text.encode("utf-8"), overwrite=overwrite)

    def plot(self) -> DeviceTopologyPlot:
        """Ask the server to draw this topology, and return the PNG.

        Sends one POST to ``/device-topology/plot`` with the topology's ``name``,
        ``device_id``, ``qubits``, ``couplings`` and ``calibrated_at``; the server stores
        nothing. A response that is not a PNG, such as an access proxy's sign-in page, raises
        ``QDashTransportError``.
        """
        options: RequestOptions = {"additional_headers": {"Accept": "image/png"}}
        with api_errors():
            raw = self._api.device_topology.with_raw_response.get_device_topology_plot(
                name=self.detail.name,
                device_id=self.detail.device_id,
                qubits=self.detail.qubits,
                couplings=self.detail.couplings,
                calibrated_at=self.detail.calibrated_at,
                request_options=options,
            )
        content = _file_content(raw.response)
        if not content.startswith(_PNG_SIGNATURE):
            raise QDashTransportError(
                f"{raw.response.status_code}: the device topology plot is not a PNG image",
                status_code=raw.response.status_code,
                headers=dict(raw.response.headers),
            )
        return DeviceTopologyPlot(content)


class DeviceTopologies:
    """Device topologies of the session's project, reached as ``QDash.device_topology``."""

    def __init__(self, api: QDashApi, config: QDashConfig) -> None:
        self._api = api
        self._config = config

    def create(
        self,
        *,
        name: str,
        device_id: str,
        qubits: Sequence[str],
        exclude_couplings: Sequence[str] | None = None,
        condition: Condition | Mapping[str, Any] | None = None,
    ) -> DeviceTopology:
        """Compute the device topology of ``qubits`` from the project's latest calibration.

        The server reads the latest calibration note of the session's project and that note's
        chip; there is no chip argument. ``name`` and ``device_id`` are labels copied into the
        result, and ``device_id`` does not select a chip. ``qubits`` are physical qubit IDs as
        strings, such as ``["0", "2", "3"]``; ``exclude_couplings`` are couplings written
        ``"control-target"``, such as ``"0-1"``. ``condition`` is a ``Condition`` from
        :mod:`qdash.sdk.types` or a mapping with the same fields, including the
        ``is_within_24h`` spelling of the request JSON; fields it does not know raise
        ``ValueError`` before anything is sent. An omitted ``exclude_couplings`` or
        ``condition`` uses the server's default.

        A device gateway's ``device_topology_request.json`` can be passed as is:
        ``create(**json.load(file))``.

        Sends one POST to ``/device-topology``, which stores nothing, and writes no file.
        The result is a snapshot: call ``create`` again for a newer calibration. A project
        without a calibration note, or whose chip is missing, makes the server fail with
        ``QDashApiError``.
        """
        request: dict[str, Any] = {
            "name": _text(name, "name"),
            "device_id": _text(device_id, "device_id"),
            "qubits": _labels(qubits, "qubits"),
        }
        if exclude_couplings is not None:
            request["exclude_couplings"] = _labels(exclude_couplings, "exclude_couplings")
        if condition is not None:
            request["condition"] = _condition(condition)
        with api_errors():
            detail = self._api.device_topology.get_device_topology(**request)
        return DeviceTopology(self._api, detail)
