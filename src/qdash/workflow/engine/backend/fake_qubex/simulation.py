"""Helpers for qxsimulator pulse-level simulation."""

# mypy: ignore-errors
# ruff: noqa

from __future__ import annotations

import json
import random
import re
from collections.abc import Collection, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_QUBIT_LABEL_PATTERN = re.compile(r"^Q(\d+)$")


def _qid_to_label(qid: int, num_qubits: int) -> str:
    return f"Q{qid:0{max(2, len(str(num_qubits)))}d}"


def _label_to_qid(label: str) -> int:
    match = _QUBIT_LABEL_PATTERN.match(label)
    if match is None:
        raise ValueError(f"Invalid Qubex qubit label {label!r}.")
    return int(match.group(1))


def _display_if_interactive(figure: Any) -> None:
    try:
        from IPython import get_ipython
        from IPython.display import display
    except Exception:
        return
    if get_ipython() is not None:
        display(figure)


def _make_figure(*, width: int | None = None, height: int | None = None) -> Any:
    try:
        import qubex.visualization as viz
    except Exception:
        try:
            import plotly.graph_objects as go
        except Exception:
            return None
        return go.Figure()
    return viz.make_figure(width=width, height=height)


def _show_figure(
    figure: Any,
    *,
    filename: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    try:
        import qubex.visualization as viz
    except Exception:
        viz = None

    try:
        if viz is not None:
            figure.show(config=viz.get_config(filename=filename, width=width, height=height))
        else:
            figure.show()
        return
    except Exception:
        pass
    _display_if_interactive(figure)


def _make_iq_scatter_figure(data: Mapping[str, Any], *, title: str | None = None) -> Any:
    try:
        import qubex.visualization as viz
    except Exception:
        viz = None
    if viz is not None:
        figure = viz.make_iq_scatter_figure(data=data, title=title)
        if getattr(figure.layout.title, "text", None) is None:
            figure.update_layout(title=title or "I/Q plane")
        return figure

    try:
        import numpy as np
        import plotly.graph_objects as go
    except Exception:
        return None

    colors = [
        (12, 93, 165, 0.8),
        (0, 185, 69, 0.8),
        (255, 149, 0, 0.8),
        (255, 44, 0, 0.8),
        (132, 91, 151, 0.8),
        (71, 71, 71, 0.8),
        (158, 158, 158, 0.8),
    ]
    figure = go.Figure()
    max_abs = 0.0
    for target, values in data.items():
        points = np.asarray(values, dtype=complex).reshape(-1)
        if points.size:
            max_abs = max(max_abs, float(np.max(np.abs(points))))
    if max_abs == 0.0:
        max_abs = 1.0
    axis_range = [-max_abs * 1.1, max_abs * 1.1]
    dtick = max_abs / 2
    for index, (target, values) in enumerate(data.items()):
        points = np.asarray(values, dtype=complex).reshape(-1)
        color = colors[index % len(colors)]
        figure.add_scatter(
            x=points.real,
            y=points.imag,
            mode="markers",
            name=target,
            text=target,
            marker={
                "size": 4,
                "color": f"rgba{color}",
            },
        )
    figure.update_layout(
        title=title or "I/Q plane",
        width=500,
        height=400,
        xaxis_title="In-phase (arb. units)",
        yaxis_title="Quadrature (arb. units)",
        margin={"l": 120, "r": 120},
        xaxis={
            "range": axis_range,
            "dtick": dtick,
            "tickformat": ".2g",
            "showticklabels": True,
            "zeroline": True,
            "zerolinecolor": "black",
            "showgrid": True,
        },
        yaxis={
            "range": axis_range,
            "scaleanchor": "x",
            "scaleratio": 1,
            "dtick": dtick,
            "tickformat": ".2g",
            "showticklabels": True,
            "zeroline": True,
            "zerolinecolor": "black",
            "showgrid": True,
        },
    )
    return figure


def _plot_iq_scatter(
    data: Mapping[str, Any],
    *,
    title: str | None = None,
    return_figure: bool = False,
) -> Any:
    figure = _make_iq_scatter_figure(data, title=title)
    if return_figure:
        return figure
    if figure is not None:
        _show_figure(figure, filename="plot_state_distribution")
    return None


def _plot_iq_series(
    *,
    target: str,
    x: Any,
    data: Any,
    title: str,
    xlabel: str,
    ylabel: str,
    filename: str,
    xaxis_type: str | None = None,
    yaxis_type: str | None = None,
    width: int | None = None,
    height: int | None = None,
    return_figure: bool = False,
    **_: Any,
) -> Any:
    try:
        import numpy as np
        import plotly.graph_objects as go
    except Exception:
        return None

    values = np.asarray(data, dtype=complex)
    figure = _make_figure(width=width, height=height)
    if figure is None:
        return None
    figure.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
    )
    if xaxis_type is not None:
        figure.update_layout(xaxis_type=xaxis_type)
    if yaxis_type is not None:
        figure.update_layout(yaxis_type=yaxis_type)
    figure.add_trace(
        go.Scatter(
            mode="markers+lines",
            x=x,
            y=values.real,
            name="I",
        )
    )
    figure.add_trace(
        go.Scatter(
            mode="markers+lines",
            x=x,
            y=values.imag,
            name="Q",
        )
    )
    if return_figure:
        return figure
    _show_figure(figure, filename=f"{filename}_{target}", width=width, height=height)
    return None


def _plot_fit_series(
    *,
    target: str,
    x: Any,
    y: Any,
    fit_y: Any,
    title: str,
    xlabel: str,
    ylabel: str,
    filename: str,
    annotation: str | None = None,
    xaxis_type: str | None = None,
    yaxis_type: str | None = None,
    width: int | None = None,
    height: int | None = None,
    return_figure: bool = False,
    **_: Any,
) -> Any:
    try:
        import numpy as np
        import plotly.graph_objects as go
    except Exception:
        return None

    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)
    fit_values = np.asarray(fit_y, dtype=float)
    x_plot = x_values * 1e-3
    figure = _make_figure(width=width, height=height)
    if figure is None:
        return None
    figure.add_trace(
        go.Scatter(
            x=x_plot,
            y=fit_values,
            mode="lines",
            name="Fit",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=x_plot,
            y=y_values,
            mode="markers",
            name="Data",
        )
    )
    if annotation:
        figure.add_annotation(
            xref="paper",
            yref="paper",
            x=0.95,
            y=0.95,
            text=annotation,
            bgcolor="rgba(255, 255, 255, 0.8)",
            showarrow=False,
        )
    figure.update_layout(
        title=f"{title} : {target}",
        xaxis_title=xlabel,
        yaxis_title=ylabel,
    )
    if xaxis_type is not None:
        figure.update_layout(xaxis_type=xaxis_type)
    if yaxis_type is not None:
        figure.update_layout(yaxis_type=yaxis_type)
    if return_figure:
        return figure
    _show_figure(figure, filename=f"{filename}_{target}", width=width, height=height)
    return None


def _plot_normalized_series(
    *,
    target: str,
    x: Any,
    y: Any,
    title: str,
    xlabel: str,
    ylabel: str = "Normalized signal",
    filename: str,
    xaxis_type: str | None = None,
    yaxis_type: str | None = None,
    width: int | None = None,
    height: int | None = None,
    return_figure: bool = False,
    **_: Any,
) -> Any:
    try:
        import numpy as np
        import plotly.graph_objects as go
    except Exception:
        return None

    figure = _make_figure(width=width, height=height)
    if figure is None:
        return None
    figure.add_trace(
        go.Scatter(
            mode="markers+lines",
            x=x,
            y=np.asarray(y, dtype=float),
        )
    )
    figure.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=ylabel,
    )
    if xaxis_type is not None:
        figure.update_layout(xaxis_type=xaxis_type)
    if yaxis_type is not None:
        figure.update_layout(yaxis_type=yaxis_type)
    figure.update_layout(yaxis_range=[-1.2, 1.2])
    if return_figure:
        return figure
    _show_figure(figure, filename=f"{filename}_{target}", width=width, height=height)
    return None


class _FallbackResult(dict):
    """Minimal Result fallback used before qubex result models are importable."""

    def __init__(
        self,
        *,
        data: Any | None = None,
        figure: Any | None = None,
        figures: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(data if isinstance(data, Mapping) else {"data": data})
        self.data = data
        self.figure = figure
        self.figures = figures or {}

    def plot(self, *args: Any, **kwargs: Any) -> None:
        if self.figure is not None:
            _display_if_interactive(self.figure)
        return None


class _FallbackExperimentResult:
    """Minimal ExperimentResult fallback for optional model imports."""

    def __init__(
        self,
        *,
        data: Mapping[str, Any],
        rabi_params: Mapping[str, Any] | None = None,
        status: str = "success",
    ) -> None:
        self.data = dict(data)
        self.rabi_params = dict(rabi_params or {})
        self.status = status

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def plot(self, *args: Any, **kwargs: Any) -> None:
        for target, value in self.data.items():
            times = getattr(value, "time_range", None)
            data = getattr(value, "data", None)
            if times is not None and data is not None:
                normalized = getattr(value, "normalized", None)
                if normalized is None:
                    import numpy as np

                    normalized = 2.0 * np.asarray(data, dtype=complex).imag
                _plot_normalized_series(
                    target=target,
                    x=times,
                    y=normalized,
                    title=f"Rabi oscillation : {target}",
                    xlabel="Drive duration (ns)",
                    ylabel="Normalized signal",
                    filename="rabi_data",
                    **kwargs,
                )
                continue
            sweep_range = getattr(value, "sweep_range", None)
            if sweep_range is not None and data is not None:
                _plot_iq_series(
                    target=target,
                    x=sweep_range,
                    data=data,
                    title=f"{getattr(value, 'title', 'Sweep result')} : {target}",
                    xlabel=getattr(value, "xlabel", "Sweep value"),
                    ylabel=getattr(value, "ylabel", "Measured signal"),
                    filename="sweep_data",
                    xaxis_type=getattr(value, "xaxis_type", "linear"),
                    yaxis_type=getattr(value, "yaxis_type", "linear"),
                    **kwargs,
                )
        return None

    def fit(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {key: getattr(value, "rabi_param", None) for key, value in self.data.items()}


class _FakeTargetMeasurement:
    def __init__(self, kerneled: Any, *, data: Any | None = None) -> None:
        self.kerneled = kerneled
        self.data = kerneled if data is None else data

    def __len__(self) -> int:
        try:
            return len(self.data)
        except TypeError:
            return 1

    def __getitem__(self, index: int) -> Any:
        return self.data[index]


class _FakeMeasureResult:
    def __init__(self, data: Mapping[str, Any], *, mode: str | None = None) -> None:
        self.data = dict(data)
        self.mode = mode or "avg"

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def plot(self, *args: Any, **kwargs: Any) -> None:
        try:
            import numpy as np
        except Exception:
            return None

        return_figure = bool(kwargs.get("return_figure", False))
        if self.mode == "single":
            data = {
                target: np.asarray(getattr(value, "kerneled", []), dtype=complex)
                for target, value in self.data.items()
            }
            return _plot_iq_scatter(data, return_figure=return_figure)

        figures = []
        for target, value in self.data.items():
            points = np.asarray(getattr(value, "kerneled", []), dtype=complex).reshape(-1)
            title = f"Readout IQ data : {target}"
            figure = _plot_iq_scatter(
                {target: points},
                title=title,
                return_figure=return_figure,
            )
            if return_figure:
                figures.append(figure)
        if return_figure:
            return figures
        return None


class _FakePulseCalibrationData:
    def __init__(
        self, *, target: str, calib_value: float, r2: float = 1.0, figure: Any = None
    ) -> None:
        self.target = target
        self.calib_value = float(calib_value)
        self.r2 = float(r2)
        self.figure = figure

    def fit(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"fig": self.figure, "r2": self.r2, "calib_value": self.calib_value}


class _FakeSweepTargetData:
    def __init__(
        self,
        target: str,
        sweep_range: Any,
        data: Any,
        *,
        title: str = "Sweep result",
        xlabel: str = "Sweep value",
        ylabel: str = "Measured signal",
        xaxis_type: str = "linear",
        yaxis_type: str = "linear",
    ) -> None:
        self.target = target
        self.sweep_range = sweep_range
        self.data = data
        self.title = title
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.xaxis_type = xaxis_type
        self.yaxis_type = yaxis_type

    def __getitem__(self, index: int) -> Any:
        if index != 0:
            raise IndexError(index)
        return self.data

    @property
    def normalized(self) -> Any:
        import numpy as np

        values = np.asarray(self.data, dtype=complex)
        return 2.0 * values.imag

    def plot(self, **kwargs: Any) -> Any:
        normalize = bool(kwargs.pop("normalize", True))
        if normalize:
            return _plot_normalized_series(
                target=self.target,
                x=self.sweep_range,
                y=self.normalized,
                title=f"{self.title} : {self.target}",
                xlabel=self.xlabel,
                ylabel="Normalized signal",
                filename="sweep_data",
                xaxis_type=self.xaxis_type,
                yaxis_type=self.yaxis_type,
                **kwargs,
            )
        return _plot_iq_series(
            target=self.target,
            x=self.sweep_range,
            data=self.data,
            title=f"{self.title} : {self.target}",
            xlabel=self.xlabel,
            ylabel=self.ylabel,
            filename="sweep_data",
            xaxis_type=self.xaxis_type,
            yaxis_type=self.yaxis_type,
            **kwargs,
        )


class _FakeSweepResult:
    def __init__(
        self,
        *,
        data: Mapping[str, Any],
        sweep_values: Any | None = None,
        results: list[Any] | None = None,
        shape: tuple[int, ...] | None = None,
        sweep_points: list[dict[str, Any]] | None = None,
    ) -> None:
        self.data = dict(data)
        self.sweep_values = sweep_values
        self.results = results or []
        self.shape = shape or ()
        self._sweep_points = sweep_points or []

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def plot(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("normalize", True)
        for target, value in self.data.items():
            value.plot(**kwargs)
        return None

    def get_sweep_point(self, index: tuple[int, ...] | int) -> dict[str, Any]:
        if isinstance(index, tuple):
            flat_index = 0
            multiplier = 1
            for size, value in zip(reversed(self.shape), reversed(index), strict=False):
                flat_index += value * multiplier
                multiplier *= size
        else:
            flat_index = index
        return self._sweep_points[flat_index]


class _NormalizedRabiData:
    def __init__(self, base: Any) -> None:
        self._base = base

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)

    def plot(self, *, normalize: bool = True, **kwargs: Any) -> Any:
        if normalize:
            return _plot_normalized_series(
                target=self.target,
                x=self.time_range,
                y=self.normalized,
                title=f"Rabi oscillation : {self.target}",
                xlabel="Drive duration (ns)",
                ylabel="Normalized signal",
                filename="rabi_data",
                **kwargs,
            )
        return self._base.plot(normalize=False, **kwargs)

    def fit(self, *args: Any, **kwargs: Any) -> Any:
        return self._base.fit(*args, **kwargs)


class _FakeControlParams:
    def __init__(self, experiment: "FakeExperiment") -> None:
        self._experiment = experiment

    def get_readout_amplitude(self, target: str) -> float:
        return float(self._experiment.params.readout_amplitude.get(target, 0.2))

    def get_control_amplitude(self, target: str) -> float:
        return float(self._experiment.params.control_amplitude.get(target, 0.0125))


@dataclass
class FakeExperiment:
    """Small simulation fixture with QUBEX-like calibration metadata."""

    name: str = "fake-qubex-two-qubit-system"
    device_id: str = "fake-qubex-two-qubit-system"
    qubit_labels: tuple[str, ...] = ("Q00", "Q01", "Q02", "Q03")
    qubit_frequencies: tuple[float, ...] = (7.157231, 8.032295, 7.812112, 6.944337)
    qubit_anharmonicities: tuple[float, ...] = (
        -0.393715,
        -0.487412,
        -0.421337,
        -0.365884,
    )
    readout_frequencies: tuple[float, ...] = (6.752, 6.903, 6.844, 6.711)
    coupling_strength: float = 0.005
    qubit_lifetime: tuple[float, float] = (20.0, 20.0)
    qubit_lifetimes: tuple[tuple[float, float], ...] | None = None
    hpi_duration: float = 24.0
    pi_duration: float = 24.0
    readout_duration: float = 1000.0
    rzx90_duration: float | None = None
    cx_duration: float | None = None
    single_qubit_fidelity: float | None = None
    two_qubit_fidelity: float | None = None
    readout_assignment_error: float | None = None
    positions: tuple[tuple[float, float], ...] = (
        (0.0, 0.0),
        (1.0, 0.0),
        (2.0, 0.0),
        (3.0, 0.0),
    )
    calibrated_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    readout_pre_margin: float = 0.0
    readout_post_margin: float = 0.0
    config_path: str = ""
    params_path: str = ""
    property_dir: Path = Path(".")
    classifier_dir: Path = Path(".")
    classifier_type: str = "gmm"
    configuration_mode: str = "ge-cr-cr"
    drag_hpi_pulses: dict[str, Any] = field(default_factory=dict, init=False)
    drag_pi_pulses: dict[str, Any] = field(default_factory=dict, init=False)
    ef_hpi_pulses: dict[str, Any] = field(default_factory=dict, init=False)
    ef_pi_pulses: dict[str, Any] = field(default_factory=dict, init=False)
    cr_params: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    cx_frame_params: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    classifiers: dict[str, Any] = field(default_factory=dict, init=False)
    readout_assignment_errors: dict[str, float] = field(default_factory=dict, init=False)
    properties: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    _rabi_params: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _connected: bool = field(default=False, init=False, repr=False)
    _clifford_generator: Any | None = field(default=None, init=False, repr=False)

    def __init__(
        self,
        *,
        chip_id: str | None = None,
        system_id: str | None = None,
        muxes: Collection[str | int] | None = None,
        qubits: Collection[str | int] | None = None,
        exclude_qubits: Collection[str | int] | None = None,
        config_dir: Path | str | None = None,
        params_dir: Path | str | None = None,
        calib_note_path: Path | str | None = None,
        calibration_valid_days: int | None = None,
        drag_hpi_duration: float | None = None,
        drag_pi_duration: float | None = None,
        readout_duration: float | None = None,
        readout_pre_margin: float | None = None,
        readout_post_margin: float | None = None,
        property_dir: Path | str | None = None,
        classifier_dir: Path | str | None = None,
        classifier_type: str | None = None,
        configuration_mode: str | None = None,
        name: str = "fake-qubex-two-qubit-system",
        device_id: str | None = None,
        qubit_labels: Collection[str] | None = None,
        qubit_frequencies: Collection[float] | None = None,
        qubit_anharmonicities: Collection[float] | None = None,
        readout_frequencies: Collection[float] | None = None,
        coupling_strength: float = 0.005,
        qubit_lifetime: tuple[float, float] = (20.0, 20.0),
        qubit_lifetimes: tuple[tuple[float, float], ...] | None = None,
        hpi_duration: float | None = None,
        pi_duration: float | None = None,
        positions: Collection[tuple[float, float]] | None = None,
        calibrated_at: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        **extra_options: Any,
    ) -> None:
        mux_labels = self._normalize_mux_labels(muxes)
        labels = tuple(
            qubit_labels
            or self._normalize_qubit_labels(qubits)
            or self._qubit_labels_from_muxes(muxes)
            or ("Q00", "Q01", "Q02", "Q03")
        )
        if exclude_qubits is not None:
            excluded = set(self._normalize_qubit_labels(exclude_qubits) or ())
            labels = tuple(label for label in labels if label not in excluded)
        n_qubits = len(labels)

        self.name = name
        self.device_id = device_id or system_id or chip_id or name
        self.qubit_labels = labels
        self._mux_labels = mux_labels or self._infer_mux_labels(labels)
        self._qubit_muxes = self._assign_qubit_muxes(labels, self._mux_labels)
        self.qubit_frequencies = self._pad_float_tuple(
            qubit_frequencies,
            (7.157231, 8.032295, 7.812112, 6.944337),
            n_qubits,
        )
        self.qubit_anharmonicities = self._pad_float_tuple(
            qubit_anharmonicities,
            (-0.393715, -0.487412, -0.421337, -0.365884),
            n_qubits,
        )
        self.readout_frequencies = self._pad_float_tuple(
            readout_frequencies,
            (6.752, 6.903, 6.844, 6.711),
            n_qubits,
        )
        self.coupling_strength = coupling_strength
        self.qubit_lifetime = qubit_lifetime
        self.qubit_lifetimes = qubit_lifetimes
        self.hpi_duration = hpi_duration or drag_hpi_duration or 24.0
        self.pi_duration = pi_duration or drag_pi_duration or 24.0
        self.readout_duration = readout_duration or 1000.0
        self.rzx90_duration = None
        self.cx_duration = None
        self.single_qubit_fidelity = None
        self.two_qubit_fidelity = None
        self.readout_assignment_error = None
        self.positions = tuple(positions or ((float(index), 0.0) for index in range(n_qubits)))
        self.calibrated_at = calibrated_at
        self.metadata = dict(metadata or {})
        self.metadata.update(
            {
                "chip_id": chip_id,
                "system_id": system_id,
                "muxes": list(self._mux_labels),
                "calib_note_path": str(calib_note_path) if calib_note_path is not None else None,
                "calibration_valid_days": calibration_valid_days,
                "extra_options": dict(extra_options),
            }
        )
        self.readout_pre_margin = readout_pre_margin or 0.0
        self.readout_post_margin = readout_post_margin or 0.0
        self.config_path = str(config_dir or "")
        self.params_path = str(params_dir or "")
        self.property_dir = Path(property_dir or ".")
        self.classifier_dir = Path(classifier_dir or ".")
        self.classifier_type = classifier_type or "gmm"
        self.configuration_mode = configuration_mode or "ge-cr-cr"
        self.drag_hpi_pulses = {}
        self.drag_pi_pulses = {}
        self.ef_hpi_pulses = {}
        self.ef_pi_pulses = {}
        self.cr_params = {}
        self.cx_frame_params = {}
        self.classifiers = {}
        self.readout_assignment_errors = {}
        self.properties = {}
        self._params = SimpleNamespace(
            readout_amplitude={label: 0.2 for label in labels},
            control_amplitude={label: 0.0125 for label in labels},
        )
        self._control_params = _FakeControlParams(self)
        self._rabi_params = {}
        self._connected = False
        self._clifford_generator = None
        self.is_fake_qubex = True

    def __getattr__(self, name: str) -> Any:
        """Expose explicit placeholders for Experiment APIs not emulated locally."""
        if name in _UNSUPPORTED_EXPERIMENT_METHODS:
            return self._unsupported_method(name)
        raise AttributeError(name)

    def _unsupported_method(self, name: str) -> Any:
        def method(*_: Any, **__: Any) -> Any:
            raise NotImplementedError(
                f"FakeExperiment.{name} is part of the hardware Experiment API "
                "and is not implemented by the local emulator."
            )

        return method

    @property
    def ctx(self) -> "FakeExperiment":
        """Return a context-like object for facade compatibility."""
        return self

    def run(self, task: Any) -> Any:
        """Run an ExperimentTask-like object against this fake experiment."""
        if callable(task):
            return task(self)
        run = getattr(task, "run", None)
        if callable(run):
            return run(self)
        raise TypeError("task must be callable or expose run(experiment).")

    def print_environment(self, verbose: bool | None = None) -> None:
        """Print a compact fake environment summary."""
        print(f"FakeExperiment(name={self.name!r}, qubits={list(self.qubit_labels)!r})")
        if verbose:
            print(f"model={self.model()!r}")

    def print_boxes(self) -> None:
        """Print the fake box inventory."""
        print("FakeExperiment has no hardware boxes.")

    def get_control_box_for_qubit(self, qubit_label: str) -> Any:
        del qubit_label
        return SimpleNamespace(traits=SimpleNamespace(ctrl_ssb="U"))

    def get_readout_box_for_qubit(self, qubit_label: str) -> Any:
        del qubit_label
        return SimpleNamespace(traits=SimpleNamespace(readout_ssb="U", readout_cnco_center=7.0e9))

    @contextmanager
    def modified_backend_settings(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        yield self

    @property
    def session_service(self) -> "FakeExperiment":
        return self

    @property
    def measurement_service(self) -> "FakeExperiment":
        return self

    @property
    def calibration_service(self) -> "FakeExperiment":
        return self

    @property
    def characterization_service(self) -> "FakeExperiment":
        return self

    @property
    def benchmarking_service(self) -> "FakeExperiment":
        return self

    @property
    def optimization_service(self) -> "FakeExperiment":
        return self

    @property
    def tool(self) -> "FakeExperiment":
        return self

    @property
    def util(self) -> "FakeExperiment":
        return self

    def discretize_time_range(self, values: Any, sampling_period: float | None = None) -> Any:
        import numpy as np

        array = np.asarray(values, dtype=float)
        if sampling_period is None or sampling_period <= 0:
            return array
        return np.unique(np.round(array / sampling_period) * sampling_period)

    def resolve_sampling_period(self, sampling_period: float | None = None) -> float:
        return float(sampling_period or self.dt * 1e9)

    def split_frequency_range(self, values: Any, chunk_size: int | None = None) -> list[Any]:
        import numpy as np

        array = np.asarray(values, dtype=float)
        if chunk_size is None or chunk_size <= 0:
            return [array]
        return [array[index : index + chunk_size] for index in range(0, len(array), chunk_size)]

    @property
    def measurement(self) -> "FakeExperiment":
        return self

    @property
    def system_manager(self) -> "FakeExperiment":
        return self

    @property
    def config_loader(self) -> "FakeExperiment":
        return self

    @property
    def experiment_system(self) -> "FakeExperiment":
        return self

    @property
    def quantum_system(self) -> Any:
        return self

    @property
    def control_params(self) -> _FakeControlParams:
        return self._control_params

    @property
    def control_system(self) -> "FakeExperiment":
        return self

    @property
    def device_controller(self) -> "FakeExperiment":
        return self

    @property
    def backend_controller(self) -> "FakeExperiment":
        return self

    @property
    def params(self) -> Any:
        return self._params

    @property
    def chip(self) -> Any:
        return SimpleNamespace(id=self.device_id, label=self.device_id)

    @property
    def chip_id(self) -> str:
        return self.device_id

    @property
    def resonator_labels(self) -> list[str]:
        return [self.resolve_read_label(label) for label in self.qubit_labels]

    @property
    def mux_labels(self) -> list[str]:
        return list(self._mux_labels)

    @property
    def qubits(self) -> dict[str, Any]:
        return {label: self.get_target(label) for label in self.qubit_labels}

    @property
    def resonators(self) -> dict[str, Any]:
        return {label: self.get_target(label) for label in self.resonator_labels}

    @property
    def targets(self) -> dict[str, Any]:
        return self.available_targets

    @property
    def available_targets(self) -> dict[str, Any]:
        labels = list(self.qubit_labels) + self.resonator_labels + self.cr_labels
        return {label: self.get_target(label) for label in labels}

    @property
    def ge_targets(self) -> dict[str, Any]:
        return self.qubits

    @property
    def ef_targets(self) -> dict[str, Any]:
        return {}

    @property
    def cr_targets(self) -> dict[str, Any]:
        return {label: self.get_target(label) for label in self.cr_labels}

    @property
    def cr_labels(self) -> list[str]:
        return [f"{control}-{target}" for control, target in self.cr_pairs]

    @property
    def cr_pairs(self) -> list[tuple[str, str]]:
        if len(self.qubit_labels) < 2:
            return []
        return [(self.qubit_labels[0], self.qubit_labels[1])]

    @property
    def edge_pairs(self) -> list[tuple[str, str]]:
        return self.cr_pairs

    @property
    def edge_labels(self) -> list[str]:
        return self.cr_labels

    @property
    def boxes(self) -> dict[str, Any]:
        return {}

    @property
    def box_ids(self) -> list[str]:
        return []

    @property
    def calib_note(self) -> Any:
        return SimpleNamespace(save=lambda *args, **kwargs: None)

    @property
    def note(self) -> dict[str, Any]:
        return {}

    @property
    def state_centers(self) -> dict[str, dict[int, complex]]:
        return {label: {0: complex(-1.0, 0.0), 1: complex(1.0, 0.0)} for label in self.qubit_labels}

    @property
    def reference_phases(self) -> dict[str, float]:
        return {label: 0.0 for label in self.qubit_labels}

    @property
    def drag_hpi_duration(self) -> float:
        return self.hpi_duration

    @property
    def drag_pi_duration(self) -> float:
        return self.pi_duration

    @property
    def hpi_pulse(self) -> dict[str, Any]:
        return self.drag_hpi_pulse

    @property
    def pi_pulse(self) -> dict[str, Any]:
        return self.drag_pi_pulse

    @property
    def drag_hpi_pulse(self) -> dict[str, Any]:
        self._ensure_default_drag_pulses(include_hpi=True, include_pi=False)
        return self.drag_hpi_pulses

    @property
    def drag_pi_pulse(self) -> dict[str, Any]:
        self._ensure_default_drag_pulses(include_hpi=False, include_pi=True)
        return self.drag_pi_pulses

    @property
    def ef_hpi_pulse(self) -> dict[str, Any]:
        return self.ef_hpi_pulses

    @property
    def ef_pi_pulse(self) -> dict[str, Any]:
        return self.ef_pi_pulses

    @property
    def cr_pulse(self) -> dict[str, Any]:
        return {
            label: self.zx90(*self.cr_pair(label))
            for label in self.cr_labels
            if label in self.cr_params
        }

    @property
    def rabi_params(self) -> dict[str, Any]:
        return dict(self._rabi_params)

    @property
    def ge_rabi_params(self) -> dict[str, Any]:
        return self.rabi_params

    @property
    def ef_rabi_params(self) -> dict[str, Any]:
        return {key: value for key, value in self._rabi_params.items() if self._is_ef_label(key)}

    def model(self) -> dict[str, Any]:
        """Build the internal emulator model used by qxsimulator adapters."""
        qubits = [
            self._qubit_topology(index, label) for index, label in enumerate(self.qubit_labels)
        ]
        topology: dict[str, Any] = {
            "name": self.name,
            "device_id": self.device_id,
            "qubits": qubits,
            "couplings": [self._coupling_topology()] if len(self.qubit_labels) >= 2 else [],
        }
        if self.calibrated_at is not None:
            topology["calibrated_at"] = self.calibrated_at
        if self.metadata:
            topology["metadata"] = dict(self.metadata)
        return topology

    def write_model(
        self,
        path: str | Path,
    ) -> Path:
        """Write the internal emulator model as JSON."""
        output_path = Path(path)
        topology = self.model()
        output_path.write_text(
            json.dumps(topology, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return output_path

    def load_property(self, property_name: str) -> dict[str, Any]:
        """Load an in-memory fake property table."""
        return dict(self.properties.get(property_name, {}))

    def save_property(
        self,
        property_name: str,
        data: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Save an in-memory fake property table."""
        self.properties[property_name] = dict(data or kwargs)

    def load_calib_note(self, path: Path | str | None = None) -> None:
        """Accept calib-note reload calls for facade compatibility."""
        if path is not None:
            self.metadata["calib_note_path"] = str(path)

    def get_qubit_label(self, index: int) -> str:
        physical_label = _qid_to_label(index, 10)
        if physical_label in self.qubit_labels:
            return physical_label
        if 0 <= index < len(self.qubit_labels):
            return self.qubit_labels[index]
        return physical_label

    def get_qubit(self, target: str) -> Any:
        label = self._ge_label(target)
        index = self.qubit_labels.index(label)
        return SimpleNamespace(
            label=label,
            frequency=self.qubit_frequencies[index],
            anharmonicity=self.qubit_anharmonicities[index],
        )

    def get_resonator_label(self, index: int) -> str:
        return self.resolve_read_label(self.get_qubit_label(index))

    def get_cr_label(
        self,
        control_qubit: str | int,
        target_qubit: str | int,
    ) -> str:
        control = (
            self.get_qubit_label(control_qubit)
            if isinstance(control_qubit, int)
            else str(control_qubit)
        )
        target = (
            self.get_qubit_label(target_qubit)
            if isinstance(target_qubit, int)
            else str(target_qubit)
        )
        return f"{control}-{target}"

    def get_cr_pairs(
        self,
        qubits: Collection[str] | str | None = None,
        *,
        directed: bool | None = True,
    ) -> list[tuple[str, str]]:
        pairs = list(self.cr_pairs)
        if not directed:
            pairs = pairs + [(target, control) for control, target in pairs]
        if qubits is None:
            return pairs
        selected = set(self._target_labels(qubits))
        return [pair for pair in pairs if pair[0] in selected or pair[1] in selected]

    def get_cr_labels(
        self,
        qubits: Collection[str] | str | None = None,
        *,
        directed: bool | None = True,
    ) -> list[str]:
        return [
            self.get_cr_label(control, target)
            for control, target in self.get_cr_pairs(qubits, directed=directed)
        ]

    def get_edge_pairs(self, qubits: Collection[str] | str | None = None) -> list[tuple[str, str]]:
        return self.get_cr_pairs(qubits, directed=False)

    def get_edge_labels(self, qubits: Collection[str] | str | None = None) -> list[str]:
        return [
            self.get_cr_label(control, target) for control, target in self.get_edge_pairs(qubits)
        ]

    def cr_pair(self, cr_label: str) -> tuple[str, str]:
        control, target = cr_label.split("-", 1)
        return control, target

    def get_rabi_param(self, target: str, transition: str | None = None) -> Any:
        label = self._resolve_rabi_label(target, transition=transition)
        return self._rabi_params.get(label)

    def store_rabi_params(self, params: Mapping[str, Any] | None = None, **kwargs: Any) -> None:
        values = dict(params or kwargs)
        self._rabi_params.update(values)
        self.properties["rabi_params"] = dict(self._rabi_params)

    def get_spectators(self, targets: Collection[str] | str | None = None) -> list[str]:
        selected = set(self._target_labels(targets)) if targets is not None else set()
        return [label for label in self.qubit_labels if label not in selected]

    def get_confusion_matrix(self, target: str) -> Any:
        import numpy as np

        error = self.readout_assignment_errors.get(target, self.readout_assignment_error) or 0.0
        half = error / 2.0
        return np.array([[1.0 - half, half], [half, 1.0 - half]], dtype=float)

    def get_inverse_confusion_matrix(self, target: str) -> Any:
        import numpy as np

        return np.linalg.inv(self.get_confusion_matrix(target))

    def is_connected(self) -> bool:
        return self._connected

    def connect(self, *args: Any, **kwargs: Any) -> "FakeExperiment":
        self._connected = True
        return self

    def disconnect(self) -> None:
        self._connected = False

    def check_status(self) -> None:
        return None

    def linkup(self, *args: Any, **kwargs: Any) -> None:
        self._connected = True

    def resync_clocks(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def configure(self, *args: Any, **kwargs: Any) -> None:
        self._connected = True

    def reload(self) -> None:
        return None

    def reset_awg_and_capunits(self, *args: Any, **kwargs: Any) -> None:
        return None

    def register_custom_target(self, label: str, target: Any | None = None, **kwargs: Any) -> Any:
        resolved = target or SimpleNamespace(label=label, **kwargs)
        self.properties.setdefault("custom_targets", {})[label] = resolved
        return resolved

    @contextmanager
    def modified_frequencies(self, *args: Any, **kwargs: Any) -> Any:
        yield self

    def save_calib_note(self, path: Path | str | None = None) -> None:
        if path is not None:
            Path(path).write_text(json.dumps(self.model(), indent=2) + "\n", encoding="utf-8")

    def save_defaults(self) -> None:
        return None

    def clear_defaults(self) -> None:
        self.properties.clear()

    def delete_defaults(self) -> None:
        self.clear_defaults()

    def load_record(self, path: Path | str) -> Any:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def validate_rabi_params(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def get_hpi_pulse(self, target: str, *args: Any, **kwargs: Any) -> Any:
        return self.x90(target)

    def get_pi_pulse(self, target: str, *args: Any, **kwargs: Any) -> Any:
        return self.x180(target)

    def get_drag_hpi_pulse(self, target: str, *args: Any, **kwargs: Any) -> Any:
        return self.x90(target)

    def get_drag_pi_pulse(self, target: str, *args: Any, **kwargs: Any) -> Any:
        return self.x180(target)

    def get_pulse_for_state(self, target: str, state: int | str, *args: Any, **kwargs: Any) -> Any:
        return self.x180(target) if str(state) in {"1", "e"} else self.x90(target).scaled(0.0)

    def calc_control_amplitude(
        self,
        target: str,
        rabi_rate: float | None = None,
        *,
        angle: float | None = None,
        **_: Any,
    ) -> float:
        del target
        if rabi_rate is None:
            if angle is not None:
                return float(angle) / self.pi_duration
            rabi_rate = 1.0 / (2.0 * self.pi_duration)
        return float(rabi_rate) * 2.0 * self.pi_duration

    def calc_control_amplitudes(
        self,
        targets: Collection[str] | str | None = None,
        rabi_rate: float | None = None,
        **kwargs: Any,
    ) -> dict[str, float]:
        return {
            target: self.calc_control_amplitude(target, rabi_rate=rabi_rate, **kwargs)
            for target in self._target_labels(targets)
        }

    def calc_rabi_rate(self, target: str, amplitude: float = 1.0, **_: Any) -> float:
        del target
        return float(amplitude) / (2.0 * self.pi_duration)

    def calc_rabi_rates(
        self,
        targets: Collection[str] | str | None = None,
        amplitude: float = 1.0,
        **kwargs: Any,
    ) -> dict[str, float]:
        return {
            target: self.calc_rabi_rate(target, amplitude=amplitude, **kwargs)
            for target in self._target_labels(targets)
        }

    def _default_drag_pulse(self, target: str, *, angle: float) -> Any:
        import numpy as np
        from qxpulse import Drag

        ge_target = self._ge_label(target)
        index = self.qubit_labels.index(ge_target)
        duration = self.hpi_duration if angle < np.pi else self.pi_duration
        beta = -0.5 / (2.0 * np.pi * self.qubit_anharmonicities[index])
        return Drag(
            duration=duration,
            amplitude=angle / np.pi,
            beta=beta,
            type="Gaussian",
        )

    def _ensure_default_drag_pulses(
        self,
        targets: Collection[str] | str | None = None,
        *,
        include_hpi: bool = True,
        include_pi: bool = True,
    ) -> None:
        for target in self._target_labels(targets):
            if include_hpi and target not in self.drag_hpi_pulses:
                self.drag_hpi_pulses[target] = self._default_drag_pulse(
                    target,
                    angle=1.5707963267948966,
                )
            if include_pi and target not in self.drag_pi_pulses:
                self.drag_pi_pulses[target] = self._default_drag_pulse(
                    target,
                    angle=3.141592653589793,
                )

    def calibrate_drag_hpi_pulse(
        self,
        targets: Collection[str] | str | None = None,
        *,
        repetitions: int = 20,
        plot: bool | None = True,
        **_: Any,
    ) -> Any:
        """Calibrate DRAG half-pi pulses with an experiment-like API."""
        try:
            np, _pd, qx, _qt, Result, _StateClassifierGMM, Control, QuantumSimulator = (
                _simulation_dependencies()
            )
        except ImportError:
            return self._lightweight_drag_calibration(targets, angle=1.5707963267948966)
        simulator = QuantumSimulator(self._qx_system())
        target_labels = self._target_labels(targets)
        data: dict[str, Any] = {}
        figures: dict[str, Any] = {}
        for target in target_labels:
            index = self.qubit_labels.index(target)
            beta = -0.5 / (2 * np.pi * self.qubit_anharmonicities[index])
            hpi_pulse = self._area_normalized_drag(self.hpi_duration, np.pi / 2, beta)
            pi_pulse = self._area_normalized_drag(self.pi_duration, np.pi, beta)
            self.drag_hpi_pulses[target] = hpi_pulse
            self.drag_pi_pulses[target] = pi_pulse
            repeat_result = self.repeat_sequence(
                {target: hpi_pulse},
                repetitions=repetitions,
                plot=plot,
                _simulator=simulator,
            )
            repeat_df = repeat_result["dataframe"]
            data[target] = {
                "target": target,
                "duration": self.hpi_duration,
                "amplitude": float(np.max(hpi_pulse.real)),
                "beta": float(beta),
                "repeat": repeat_df,
            }
            if repeat_result.figure is not None:
                figures[target] = repeat_result.figure
        return Result(data=data, figures=figures)

    def calibrate_drag_pi_pulse(
        self,
        targets: Collection[str] | str | None = None,
        *,
        plot: bool | None = True,
        **_: Any,
    ) -> Any:
        """Calibrate DRAG pi pulses from the same DRAG beta estimate."""
        try:
            (
                np,
                _pd,
                _qx,
                _qt,
                Result,
                _StateClassifierGMM,
                _Control,
                _QuantumSimulator,
            ) = _simulation_dependencies()
        except ImportError:
            return self._lightweight_drag_calibration(targets, angle=3.141592653589793)
        data: dict[str, Any] = {}
        for target in self._target_labels(targets):
            index = self.qubit_labels.index(target)
            beta = -0.5 / (2 * np.pi * self.qubit_anharmonicities[index])
            pi_pulse = self._area_normalized_drag(self.pi_duration, np.pi, beta)
            self.drag_pi_pulses[target] = pi_pulse
            data[target] = {
                "target": target,
                "duration": self.pi_duration,
                "amplitude": float(np.max(pi_pulse.real)),
                "beta": float(beta),
            }
        return Result(data=data)

    def obtain_cr_params(
        self,
        control_qubit: str,
        target_qubit: str,
        *,
        tomography_duration: float = 400.0,
        tomography_samples: int = 80,
        plot: bool | None = True,
        **_: Any,
    ) -> Any:
        """Obtain echoed ZX90 CR parameters with a QUBEX-like API."""
        try:
            (
                np,
                _pd,
                qx,
                _qt,
                Result,
                _StateClassifierGMM,
                _Control,
                QuantumSimulator,
            ) = _simulation_dependencies()
        except ImportError:
            return self._lightweight_cr_params(control_qubit, target_qubit)
        simulator = QuantumSimulator(self._qx_system())
        control_index = self.qubit_labels.index(control_qubit)
        target_index = self.qubit_labels.index(target_qubit)
        frequency_diff = (
            self.qubit_frequencies[control_index] - self.qubit_frequencies[target_index]
        )
        cr_amplitude_max = 0.75 * abs(frequency_diff)
        cr_phase_offset = 0.25 * np.pi
        cr_ramptime = 16
        xt_ratio = 0.01
        xt_phase_offset = 0.5 * np.pi
        rotary_multiple = 17
        duration_unit = 16
        pi_pulse = self.drag_pi_pulses.get(control_qubit)
        if pi_pulse is None:
            self.calibrate_drag_pi_pulse([control_qubit], plot=False)
            pi_pulse = self.drag_pi_pulses[control_qubit]

        def cr_sequence(
            *,
            duration: float,
            cr_amplitude: float,
            cr_phase: float,
            cancel_amplitude: float,
            cancel_phase: float,
            echo: bool,
        ) -> Any:
            cr_beta = -1 / (2 * np.pi * frequency_diff)
            cr_waveform = qx.pulse.FlatTop(
                duration=duration,
                amplitude=2 * np.pi * cr_amplitude,
                tau=cr_ramptime,
                phase=cr_phase + cr_phase_offset,
                beta=cr_beta,
            )
            cancel_waveform = qx.pulse.FlatTop(
                duration=duration,
                amplitude=2 * np.pi * cancel_amplitude,
                tau=cr_ramptime,
                phase=cancel_phase,
                beta=-1 / (2 * np.pi * self.qubit_anharmonicities[target_index]),
            )
            crosstalk_waveform = qx.pulse.FlatTop(
                duration=duration,
                amplitude=2 * np.pi * cr_amplitude * xt_ratio,
                tau=cr_ramptime,
                phase=xt_phase_offset,
                beta=cr_beta,
            )
            channels = [
                qx.PulseChannel(
                    label="Control",
                    frequency=self.qubit_frequencies[control_index],
                    target=control_qubit,
                ),
                qx.PulseChannel(
                    label="CR",
                    frequency=self.qubit_frequencies[target_index],
                    target=control_qubit,
                ),
                qx.PulseChannel(
                    label="Crosstalk",
                    frequency=self.qubit_frequencies[target_index],
                    target=target_qubit,
                ),
                qx.PulseChannel(
                    label="Target",
                    frequency=self.qubit_frequencies[target_index],
                    target=target_qubit,
                ),
            ]
            with qx.PulseSchedule(channels) as cr:
                cr.add("CR", cr_waveform)
                cr.add("Crosstalk", crosstalk_waveform)
                cr.add("Target", cancel_waveform)
            if not echo:
                return cr
            with qx.PulseSchedule(channels) as ecr:
                ecr.call(cr)
                ecr.barrier()
                ecr.add("Control", pi_pulse)
                ecr.barrier()
                ecr.call(cr.scaled(-1))
                ecr.barrier()
                ecr.add("Control", pi_pulse)
            return ecr

        def simulate_cr(
            *,
            cr_amplitude: float,
            cr_phase: float,
            cancel_amplitude: float,
            cancel_phase: float,
            duration: float,
            echo: bool,
            control_state: str,
            n_samples: int = 120,
        ) -> Any:
            return simulator.mesolve(
                controls=cr_sequence(
                    duration=duration,
                    cr_amplitude=cr_amplitude,
                    cr_phase=cr_phase,
                    cancel_amplitude=cancel_amplitude,
                    cancel_phase=cancel_phase,
                    echo=echo,
                ),
                initial_state={control_qubit: control_state, target_qubit: "0"},
                n_samples=n_samples,
            )

        def hamiltonian_tomography(
            *,
            cr_amplitude: float,
            cr_phase: float,
            cancel_amplitude: float,
            cancel_phase: float,
        ) -> dict[str, Any]:
            result_0 = simulate_cr(
                cr_amplitude=cr_amplitude,
                cr_phase=cr_phase,
                cancel_amplitude=cancel_amplitude,
                cancel_phase=cancel_phase,
                duration=tomography_duration,
                echo=False,
                control_state="0",
                n_samples=tomography_samples,
            )
            result_1 = simulate_cr(
                cr_amplitude=cr_amplitude,
                cr_phase=cr_phase,
                cancel_amplitude=cancel_amplitude,
                cancel_phase=cancel_phase,
                duration=tomography_duration,
                echo=False,
                control_state="1",
                n_samples=tomography_samples,
            )
            times = result_0.times
            vectors_0 = result_0.get_bloch_vectors(target_qubit)
            vectors_1 = result_1.get_bloch_vectors(target_qubit)
            indices = (times >= cr_ramptime) & (times < times[-1] - cr_ramptime)
            times_fit = times[indices] - cr_ramptime * 0.5
            fit_0 = qx.fit.fit_rotation(times_fit, vectors_0[indices], plot=False)
            fit_1 = qx.fit.fit_rotation(times_fit, vectors_1[indices], plot=False)
            omega = np.concatenate(
                [
                    0.5 * (fit_0["Omega"] + fit_1["Omega"]),
                    0.5 * (fit_0["Omega"] - fit_1["Omega"]),
                ]
            )
            coeffs = dict(
                zip(
                    ["IX", "IY", "IZ", "ZX", "ZY", "ZZ"],
                    omega / (2 * np.pi),
                    strict=True,
                )
            )
            xt_rotation = coeffs["IX"] + 1j * coeffs["IY"]
            cr_rotation = coeffs["ZX"] + 1j * coeffs["ZY"]
            return {
                "coeffs": coeffs,
                "xt_rotation": xt_rotation,
                "cr_rotation": cr_rotation,
                "zx90_duration": float(1 / (4 * np.abs(cr_rotation))),
            }

        tomography_1 = hamiltonian_tomography(
            cr_amplitude=cr_amplitude_max,
            cr_phase=0.0,
            cancel_amplitude=0.0,
            cancel_phase=0.0,
        )
        cr_phase = -float(np.angle(tomography_1["cr_rotation"]))
        tomography_2 = hamiltonian_tomography(
            cr_amplitude=cr_amplitude_max,
            cr_phase=cr_phase,
            cancel_amplitude=0.0,
            cancel_phase=0.0,
        )
        cancel_pulse_max = -tomography_2["xt_rotation"]
        tomography_3 = hamiltonian_tomography(
            cr_amplitude=cr_amplitude_max,
            cr_phase=cr_phase,
            cancel_amplitude=float(np.abs(cancel_pulse_max)),
            cancel_phase=float(np.angle(cancel_pulse_max)),
        )
        zx_rate = float(tomography_3["coeffs"]["ZX"])
        cr_duration = float(
            ((tomography_3["zx90_duration"] / 2 + cr_ramptime) // duration_unit + 1) * duration_unit
        )

        def measure_target_z(cr_amplitude: float) -> float:
            ratio = cr_amplitude / cr_amplitude_max
            cancel_pulse = (cancel_pulse_max + zx_rate * rotary_multiple) * ratio
            result = simulate_cr(
                cr_amplitude=cr_amplitude,
                cr_phase=cr_phase,
                cancel_amplitude=float(np.abs(cancel_pulse)),
                cancel_phase=float(np.angle(cancel_pulse)),
                duration=cr_duration,
                echo=True,
                control_state="0",
                n_samples=2,
            )
            return float(result.get_bloch_vectors(target_qubit)[-1][2])

        amplitude_range = np.linspace(cr_amplitude_max * 0.8, cr_amplitude_max * 1.2, 20)
        z_values = np.array([measure_target_z(float(amplitude)) for amplitude in amplitude_range])
        fit_result = qx.fit.fit_polynomial(
            x=amplitude_range,
            y=z_values,
            degree=3,
            plot=False,
        )
        cr_amplitude = float(fit_result["root"])
        ratio = cr_amplitude / cr_amplitude_max
        cancel_pulse = (cancel_pulse_max + zx_rate * rotary_multiple) * ratio
        cr_label = f"{control_qubit}-{target_qubit}"
        cr_param = {
            "control": control_qubit,
            "target": target_qubit,
            "duration": cr_duration,
            "ramptime": cr_ramptime,
            "cr_amplitude": cr_amplitude,
            "cr_phase": cr_phase,
            "cancel_amplitude": float(np.abs(cancel_pulse)),
            "cancel_phase": float(np.angle(cancel_pulse)),
            "cr_amplitude_max": cr_amplitude_max,
        }
        self.cr_params[cr_label] = cr_param
        self.rzx90_duration = 2.0 * cr_duration + 2.0 * self.pi_duration
        self.cx_duration = self.rzx90_duration + self.hpi_duration
        figures = {}
        if plot:
            fig = qx.viz.make_plot_figure(
                x=amplitude_range,
                y=z_values,
                title="Echoed ZX90 amplitude calibration",
                xlabel="CR amplitude [GHz]",
                ylabel="target <Z>",
                ylim=[-1.1, 1.1],
            )
            fig.add_hline(y=0.0, line_dash="dot", line_color="#64748b")
            figures["amplitude"] = fig
        return Result(
            data={
                "cr_param": cr_param,
                "tomography": [tomography_1, tomography_2, tomography_3],
                "amplitude_scan": {
                    "amplitudes": amplitude_range,
                    "z_values": z_values,
                    "fit": fit_result,
                },
            },
            figure=figures.get("amplitude"),
            figures=figures,
        )

    def calibrate_zx90(
        self,
        control_qubit: str,
        target_qubit: str,
        *,
        amplitude_range: Any | None = None,
        n_repetitions: int = 4,
        n_points: int = 15,
        plot: bool | None = True,
        **_: Any,
    ) -> Any:
        """Fine tune the calibrated echoed ZX90 amplitude with qxsimulator."""
        try:
            (
                np,
                _pd,
                qx,
                _qt,
                Result,
                _StateClassifierGMM,
                _Control,
                QuantumSimulator,
            ) = _simulation_dependencies()
        except ImportError:
            if f"{control_qubit}-{target_qubit}" not in self.cr_params:
                self._lightweight_cr_params(control_qubit, target_qubit)
            return self._result(
                data={
                    "cr_param": dict(self.cr_params[f"{control_qubit}-{target_qubit}"]),
                    "fit": {
                        "argmin": self.cr_params[f"{control_qubit}-{target_qubit}"]["cr_amplitude"]
                    },
                }
            )
        cr_label = f"{control_qubit}-{target_qubit}"
        if cr_label not in self.cr_params:
            self.obtain_cr_params(control_qubit, target_qubit, plot=False)
        param = self.cr_params[cr_label]
        base_amplitude = float(param["cr_amplitude"])
        if amplitude_range is None:
            amplitude_range = np.linspace(base_amplitude * 0.9, base_amplitude * 1.1, n_points)
        else:
            amplitude_range = np.asarray(amplitude_range, dtype=float)
        simulator = QuantumSimulator(self._qx_system(include_decoherence=False))
        original = dict(param)

        ideal_p1 = np.array(
            [np.sin(repeats * np.pi / 4) ** 2 for repeats in range(1, n_repetitions + 1)]
        )

        def repeated_p1(amplitude: float) -> list[float]:
            ratio = float(amplitude) / base_amplitude
            param["cr_amplitude"] = float(amplitude)
            param["cancel_amplitude"] = float(original["cancel_amplitude"]) * ratio
            values = []
            for repeats in range(1, n_repetitions + 1):
                sequence = self.zx90(control_qubit, target_qubit).repeated(repeats)
                result = simulator.mesolve(
                    sequence,
                    initial_state={control_qubit: "0", target_qubit: "0"},
                    n_samples=2,
                )
                populations = result._get_population(result.get_substates(target_qubit)[-1])
                values.append(float(np.real(populations[1])))
            return values

        p1_values = np.array(
            [repeated_p1(float(amplitude)) for amplitude in amplitude_range],
            dtype=float,
        )
        errors = np.mean((p1_values - ideal_p1) ** 2, axis=1)
        fit_degree = min(2, len(amplitude_range) - 1)
        coefficients = np.polyfit(amplitude_range, errors, deg=fit_degree)
        tuned_amplitude = float(amplitude_range[np.argmin(errors)])
        if fit_degree == 2 and coefficients[0] > 0:
            tuned_amplitude = float(-coefficients[1] / (2 * coefficients[0]))
        fit_result = {
            "degree": fit_degree,
            "coefficients": coefficients,
            "argmin": tuned_amplitude,
        }
        if not (
            float(np.min(amplitude_range)) <= tuned_amplitude <= float(np.max(amplitude_range))
        ):
            tuned_amplitude = float(amplitude_range[np.argmin(errors)])
        ratio = tuned_amplitude / base_amplitude
        param["cr_amplitude"] = tuned_amplitude
        param["cancel_amplitude"] = float(original["cancel_amplitude"]) * ratio
        self.rzx90_duration = 2.0 * float(param["duration"]) + 2.0 * self.pi_duration
        self.cx_duration = self.rzx90_duration + self.hpi_duration

        figures = {}
        if plot:
            fig = qx.viz.make_plot_figure(
                x=amplitude_range,
                y=errors,
                title="ZX90 amplitude fine tune",
                xlabel="CR amplitude [GHz]",
                ylabel=f"Repeat-sequence MSE ({n_repetitions} repeats)",
            )
            fig.add_vline(x=tuned_amplitude, line_dash="dot", line_color="#dc2626")
            figures["amplitude"] = fig

        return Result(
            data={
                "cr_param": dict(param),
                "amplitudes": amplitude_range,
                "p1_values": p1_values,
                "ideal_p1_values": ideal_p1,
                "errors": errors,
                "fit": fit_result,
            },
            figure=figures.get("amplitude"),
            figures=figures,
        )

    def correct_rabi_params(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"corrected": "rabi_params"})

    def correct_classifiers(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"corrected": "classifiers"})

    def correct_cr_params(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"corrected": "cr_params"})

    def correct_calibration(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"corrected": "calibration"})

    def calibrate_default_pulse(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.calibrate_drag_hpi_pulse(targets, **kwargs)

    def calibrate_hpi_pulse(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        del kwargs
        return self._pulse_calibration_result(targets, angle=1.5707963267948966)

    def calibrate_pi_pulse(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        del kwargs
        return self._pulse_calibration_result(targets, angle=3.141592653589793)

    def _pulse_calibration_result(
        self,
        targets: Collection[str] | str | None = None,
        *,
        angle: float,
    ) -> Any:
        import numpy as np

        data: dict[str, Any] = {}
        figures: dict[str, Any] = {}
        duration = self.hpi_duration if angle < np.pi else self.pi_duration
        amplitude = 0.5 if angle < np.pi else 1.0
        x = np.linspace(0.0, 2.0 * duration, 25)
        y = np.sin(np.pi * x / max(2.0 * duration, 1.0))
        for target in self._target_labels(targets):
            if angle < np.pi:
                self.drag_hpi_pulses[target] = self._default_drag_pulse(target, angle=angle)
            else:
                self.drag_pi_pulses[target] = self._default_drag_pulse(target, angle=angle)
            figure = _plot_normalized_series(
                target=target,
                x=x,
                y=y,
                title=("HPI pulse calibration" if angle < np.pi else "PI pulse calibration"),
                xlabel="Drive duration (ns)",
                ylabel="Normalized signal",
                filename="pulse_calibration",
                return_figure=True,
            )
            figures[target] = figure
            data[target] = _FakePulseCalibrationData(
                target=target, calib_value=amplitude, r2=1.0, figure=figure
            )
        return self._result(data=data, figures=figures, figure=next(iter(figures.values()), None))

    def calibrate_ef_pulse(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.calibrate_ef_hpi_pulse(targets, **kwargs)

    def calibrate_ef_hpi_pulse(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        result = self.calibrate_drag_hpi_pulse(targets, **kwargs)
        for target in self._target_labels(targets):
            self.ef_hpi_pulses[target] = self.drag_hpi_pulses[target]
        return result

    def calibrate_ef_pi_pulse(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        result = self.calibrate_drag_pi_pulse(targets, **kwargs)
        for target in self._target_labels(targets):
            self.ef_pi_pulses[target] = self.drag_pi_pulses[target]
        return result

    def calibrate_drag_amplitude(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.calibrate_drag_hpi_pulse(targets, **kwargs)

    def calibrate_drag_beta(
        self,
        targets: Collection[str] | str | None = None,
        **_: Any,
    ) -> Any:
        import numpy as np

        data = {}
        for target in self._target_labels(targets):
            index = self.qubit_labels.index(target)
            data[target] = -0.5 / (2 * np.pi * self.qubit_anharmonicities[index])
        return self._result(data=data)

    def measure_cr_dynamics(
        self,
        control_qubit: str,
        target_qubit: str,
        **kwargs: Any,
    ) -> Any:
        return self.obtain_cr_params(control_qubit, target_qubit, **kwargs)

    def measure_cr_crosstalk(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"crosstalk": 0.0})

    def cr_crosstalk_hamiltonian_tomography(self, *args: Any, **kwargs: Any) -> Any:
        return self.measure_cr_crosstalk(*args, **kwargs)

    def cr_hamiltonian_tomography(
        self,
        control_qubit: str,
        target_qubit: str,
        **kwargs: Any,
    ) -> Any:
        return self.obtain_cr_params(control_qubit, target_qubit, **kwargs)

    def update_cr_params(self, control_qubit: str, target_qubit: str, **params: Any) -> Any:
        label = f"{control_qubit}-{target_qubit}"
        current = self.cr_params.setdefault(label, {})
        current.update(params)
        return self._result(data={"cr_param": dict(current)})

    def calibrate_1q(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.calibrate_drag_hpi_pulse(targets, **kwargs)

    def calibrate_2q(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        results = {}
        for control, target in self.get_cr_pairs(targets):
            results[f"{control}-{target}"] = self.obtain_cr_params(control, target, **kwargs)
        return self._result(data=results)

    def zx90(self, control_qubit: str, target_qubit: str) -> Any:
        """Build the calibrated echoed ZX90 pulse schedule."""
        try:
            (
                np,
                _pd,
                qx,
                _qt,
                _Result,
                _StateClassifierGMM,
                _Control,
                _QuantumSimulator,
            ) = _simulation_dependencies()
        except ImportError:
            return self._lightweight_zx90(control_qubit, target_qubit)
        cr_label = f"{control_qubit}-{target_qubit}"
        if cr_label not in self.cr_params:
            self.obtain_cr_params(control_qubit, target_qubit, plot=False)
        param = self.cr_params[cr_label]
        control_index = self.qubit_labels.index(control_qubit)
        target_index = self.qubit_labels.index(target_qubit)
        frequency_diff = (
            self.qubit_frequencies[control_index] - self.qubit_frequencies[target_index]
        )
        pi_pulse = self.drag_pi_pulses.get(control_qubit)
        if pi_pulse is None:
            self.calibrate_drag_pi_pulse([control_qubit], plot=False)
            pi_pulse = self.drag_pi_pulses[control_qubit]
        cr_beta = -1 / (2 * np.pi * frequency_diff)
        cr_waveform = qx.pulse.FlatTop(
            duration=param["duration"],
            amplitude=2 * np.pi * param["cr_amplitude"],
            tau=param["ramptime"],
            phase=param["cr_phase"] + 0.25 * np.pi,
            beta=cr_beta,
        )
        cancel_waveform = qx.pulse.FlatTop(
            duration=param["duration"],
            amplitude=2 * np.pi * param["cancel_amplitude"],
            tau=param["ramptime"],
            phase=param["cancel_phase"],
            beta=-1 / (2 * np.pi * self.qubit_anharmonicities[target_index]),
        )
        channels = [
            qx.PulseChannel(
                label=control_qubit,
                frequency=self.qubit_frequencies[control_index],
                target=control_qubit,
            ),
            qx.PulseChannel(
                label=f"{control_qubit}-{target_qubit}",
                frequency=self.qubit_frequencies[target_index],
                target=control_qubit,
            ),
            qx.PulseChannel(
                label=target_qubit,
                frequency=self.qubit_frequencies[target_index],
                target=target_qubit,
            ),
        ]
        with qx.PulseSchedule(channels) as cr:
            cr.add(f"{control_qubit}-{target_qubit}", cr_waveform)
            cr.add(target_qubit, cancel_waveform)
        with qx.PulseSchedule(channels) as ecr:
            ecr.call(cr)
            ecr.barrier()
            ecr.add(control_qubit, pi_pulse)
            ecr.barrier()
            ecr.call(cr.scaled(-1))
            ecr.barrier()
            ecr.add(control_qubit, pi_pulse)
        return ecr

    @property
    def pulse(self) -> "FakeExperiment":
        """Expose an experiment-like pulse service."""
        return self

    @property
    def dt(self) -> float:
        """Sampling period used by the fake experiment, in seconds."""
        return 1e-9

    def x90(self, target: str) -> Any:
        self._ensure_default_drag_pulses([target], include_hpi=True, include_pi=False)
        return self.drag_hpi_pulses[target]

    def x90m(self, target: str) -> Any:
        return self.x90(target).scaled(-1)

    def x180(self, target: str) -> Any:
        self._ensure_default_drag_pulses([target], include_hpi=False, include_pi=True)
        return self.drag_pi_pulses[target]

    def y90(self, target: str) -> Any:
        import numpy as np

        return self.x90(target).shifted(0.5 * np.pi)

    def y90m(self, target: str) -> Any:
        import numpy as np

        return self.x90(target).shifted(-0.5 * np.pi)

    def y180(self, target: str) -> Any:
        import numpy as np

        return self.x180(target).shifted(0.5 * np.pi)

    def z90(self) -> Any:
        import numpy as np
        import qubex as qx

        return qx.pulse.VirtualZ(0.5 * np.pi)

    def z180(self) -> Any:
        import numpy as np
        import qubex as qx

        return qx.pulse.VirtualZ(np.pi)

    def hadamard(self, target: str) -> Any:
        import qubex as qx

        return qx.PulseArray([self.z180(), self.y90(target)])

    def readout(self, target: str) -> Any:
        import qubex as qx

        return qx.pulse.FlatTop(
            duration=self.readout_duration,
            amplitude=1.0,
            tau=min(16.0, self.readout_duration / 4.0),
            phase=0.0,
            beta=0.0,
        )

    def cx(self, control_qubit: str, target_qubit: str) -> Any:
        _np, _pd, qx, _qt, _Result, _StateClassifierGMM, _Control, _QuantumSimulator = (
            _simulation_dependencies()
        )
        zx90 = self.zx90(control_qubit, target_qubit)
        with qx.PulseSchedule(list(zx90.labels)) as schedule:
            schedule.call(zx90)
            schedule.add(control_qubit, qx.pulse.VirtualZ(-0.5 * _np.pi))
            schedule.add(target_qubit, self.x90(target_qubit).scaled(-1))
        return schedule

    def rzx(
        self,
        control_qubit: str,
        target_qubit: str,
        angle: float = 1.5707963267948966,
        **_: Any,
    ) -> Any:
        """Build a fake RZX schedule by scaling the calibrated ZX90 pulse."""
        return self.zx90(control_qubit, target_qubit).scaled(float(angle) / 1.5707963267948966)

    def rzx_gate_property(
        self,
        control_qubit: str,
        target_qubit: str,
        angle: float = 1.5707963267948966,
        **_: Any,
    ) -> dict[str, Any]:
        duration = self.rzx90_duration
        if duration is None:
            if f"{control_qubit}-{target_qubit}" not in self.cr_params:
                self.obtain_cr_params(control_qubit, target_qubit, plot=False)
            duration = self.rzx90_duration
        return {
            "gate": "rzx",
            "control": control_qubit,
            "target": target_qubit,
            "angle": float(angle),
            "duration": duration,
        }

    def cnot(
        self,
        control_qubit: str,
        target_qubit: str,
        *,
        zx90: Any | None = None,
        **_: Any,
    ) -> Any:
        """QUBEX pulse-service alias for ``cx`` with optional ZX90 injection."""
        if zx90 is None:
            return self.cx(control_qubit, target_qubit)
        _np, _pd, qx, _qt, _Result, _StateClassifierGMM, _Control, _QuantumSimulator = (
            _simulation_dependencies()
        )
        with qx.PulseSchedule(list(zx90.labels)) as schedule:
            schedule.call(zx90)
            schedule.add(control_qubit, qx.pulse.VirtualZ(-0.5 * _np.pi))
            schedule.add(target_qubit, self.x90(target_qubit).scaled(-1))
        return schedule

    def cz(self, control_qubit: str, target_qubit: str, **_: Any) -> Any:
        """Build a CZ-equivalent schedule from H-CX-H on the target."""
        _np, _pd, qx, _qt, _Result, _StateClassifierGMM, _Control, _QuantumSimulator = (
            _simulation_dependencies()
        )
        with qx.PulseSchedule([control_qubit, target_qubit]) as schedule:
            schedule.add(target_qubit, self.hadamard(target_qubit))
            schedule.call(self.cx(control_qubit, target_qubit))
            schedule.add(target_qubit, self.hadamard(target_qubit))
        return schedule

    def build_measurement_schedule(
        self,
        schedule: Any | None = None,
        *,
        targets: Collection[str] | str | None = None,
        **_: Any,
    ) -> Any:
        """Build a pulse schedule with readout pulses appended."""
        _np, _pd, qx, _qt, _Result, _StateClassifierGMM, _Control, _QuantumSimulator = (
            _simulation_dependencies()
        )
        labels = self._target_labels(targets)
        channels = list(labels) + [self.resolve_read_label(label) for label in labels]
        with qx.PulseSchedule(channels) as measurement_schedule:
            if schedule is not None:
                measurement_schedule.call(schedule)
            measurement_schedule.barrier()
            for label in labels:
                measurement_schedule.add(self.resolve_read_label(label), self.readout(label))
        return measurement_schedule

    async def run_measurement(self, *args: Any, **kwargs: Any) -> Any:
        return self.execute(*args, **kwargs)

    async def run_sweep_measurement(
        self,
        schedule: Any,
        sweep_values: Collection[Any],
        **kwargs: Any,
    ) -> Any:
        return self.sweep_parameter(schedule, values=sweep_values, **kwargs)

    async def run_ndsweep_measurement(
        self,
        schedule: Any,
        sweep_points: Mapping[str, Collection[Any]],
        sweep_axes: tuple[str, ...] | list[str] | None = None,
        **kwargs: Any,
    ) -> Any:
        del schedule
        return self._fake_ndsweep_result(
            sweep_points,
            sweep_axes,
            targets=kwargs.get("targets"),
        )

    def check_noise(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"noise": 0.0})

    def execute(
        self,
        schedule: Any | None = None,
        *,
        targets: Collection[str] | str | None = None,
        n_shots: int | None = None,
        shots: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute a schedule with qxsimulator and return state probabilities."""
        labels = self._measurement_targets(targets, schedule)
        shot_count = shots or n_shots or 1024
        simulate = kwargs.pop("simulate", None)
        use_simulator = kwargs.pop("use_simulator", None)
        return_measure_result = kwargs.get("return_measure_result", True)
        should_simulate = schedule is not None and (
            simulate is not False and use_simulator is not False
        )
        if should_simulate:
            try:
                measurement = self._simulate_measure_result(
                    schedule,
                    targets=labels,
                    shots=shot_count,
                    mode=kwargs.get("mode", "avg"),
                    initial_state=kwargs.get("initial_state"),
                    n_samples=kwargs.get("n_samples"),
                    include_decoherence=kwargs.get("include_decoherence", True),
                )
            except (ImportError, ValueError):
                if simulate is True or use_simulator is True:
                    raise
            else:
                measurement.simulated = True
                if return_measure_result or "mode" in kwargs:
                    return measurement
                return self._measurement_result_to_probabilities(
                    measurement,
                    shots=shot_count,
                )
        if "mode" in kwargs or return_measure_result:
            return self._fake_measure_result(
                labels, shots=shot_count, mode=kwargs.get("mode", "avg")
            )
        probabilities = {label: {"0": 1.0, "1": 0.0} for label in labels}
        counts = {
            "".join("0" for _ in labels): shot_count,
        }
        return self._result(
            data={
                "probabilities": probabilities,
                "counts": counts,
                "targets": labels,
                "shots": shot_count,
            }
        )

    def capture_loopback(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"samples": []})

    def measure(
        self,
        schedule: Any | None = None,
        *,
        sequence: Any | None = None,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        if schedule is None:
            schedule = sequence
        return self.execute(schedule, targets=targets, **kwargs)

    def measure_state(
        self,
        state: Mapping[str, str] | str | None = None,
        *,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        labels = self._target_labels(targets)
        probabilities = {label: {0: 1.0, 1: 0.0} for label in labels}
        if isinstance(state, Mapping):
            for label, value in state.items():
                probabilities[label] = {
                    0: float(str(value) == "0"),
                    1: float(str(value) == "1"),
                }
        return self._result(data={"probabilities": probabilities, "state": state})

    def measure_idle_states(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.measure_state("0", targets=targets, **kwargs)

    def obtain_reference_points(
        self,
        targets: Collection[str] | str | None = None,
        **_: Any,
    ) -> Any:
        labels = self._target_labels(targets)
        references = {label: {0: complex(-1.0, 0.0), 1: complex(1.0, 0.0)} for label in labels}
        return self._result(data={"reference_points": references})

    def sweep_parameter(
        self,
        sequence: Any,
        values: Collection[Any] | None = None,
        *,
        sweep_range: Collection[Any] | None = None,
        parameter_name: str = "parameter",
        plot: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        del parameter_name
        if plot is None:
            plot = True
        if values is None:
            values = sweep_range
        if values is None:
            values = []
        values_list = list(values)
        if "simulate" not in kwargs and "use_simulator" not in kwargs:
            kwargs["use_simulator"] = False
        simulate = kwargs.get("simulate")
        use_simulator = kwargs.get("use_simulator")
        results = []
        used_simulated_measurements = False
        for value in values_list:
            schedule = sequence(value) if callable(sequence) else sequence
            measurement = self.execute(schedule, **kwargs)
            results.append(measurement)
            used_simulated_measurements = used_simulated_measurements or (
                isinstance(measurement, _FakeMeasureResult)
                and (
                    bool(getattr(measurement, "simulated", False))
                    or simulate is True
                    or use_simulator is True
                )
            )
        targets = self._measurement_targets(kwargs.get("targets"), sequence)
        result_factory = (
            self._sweep_result_from_measurements
            if used_simulated_measurements
            else self._fake_sweep_result
        )
        result = result_factory(
            targets,
            values_list,
            results=results,
            title=kwargs.get("title", "Sweep result"),
            xlabel=kwargs.get("xlabel", "Sweep value"),
            ylabel=kwargs.get("ylabel", "Measured signal"),
            xaxis_type=kwargs.get("xaxis_type", "linear"),
            yaxis_type=kwargs.get("yaxis_type", "linear"),
        )
        if plot:
            result.plot()
        return result

    def _fake_measure_result(
        self,
        targets: Collection[str] | str | None = None,
        *,
        shots: int = 1024,
        mode: str | None = None,
    ) -> _FakeMeasureResult:
        import numpy as np

        labels = self._target_labels(targets)
        data = {}
        for index, target in enumerate(labels):
            center = complex(0.1 + index * 0.05, 0.2)
            if mode == "single":
                rng = np.random.default_rng(1000 + index)
                kerneled = (
                    center
                    + rng.normal(scale=0.025, size=shots)
                    + 1j * rng.normal(scale=0.025, size=shots)
                ).astype(complex)
            else:
                kerneled = np.asarray([center], dtype=complex)
            captures = [
                SimpleNamespace(data=np.asarray([center], dtype=complex), kerneled=kerneled)
            ]
            data[target] = _FakeTargetMeasurement(kerneled=kerneled, data=captures)
        return _FakeMeasureResult(data, mode=mode)

    def _fake_sweep_result(
        self,
        targets: Collection[str] | str | None,
        sweep_values: list[Any],
        *,
        results: list[Any] | None = None,
        title: str = "Sweep result",
        xlabel: str = "Sweep value",
        ylabel: str = "Measured signal",
        xaxis_type: str = "linear",
        yaxis_type: str = "linear",
    ) -> _FakeSweepResult:
        import numpy as np

        labels = self._target_labels(targets)
        values = np.asarray(sweep_values)
        data = {}
        for index, target in enumerate(labels):
            phase = np.linspace(0.0, 2.0 * np.pi, len(values)) + index * 0.35
            response = 0.5 * np.cos(phase) + 0.35j * np.sin(phase)
            data[target] = _FakeSweepTargetData(
                target,
                values,
                response,
                title=title,
                xlabel=xlabel,
                ylabel=ylabel,
                xaxis_type=xaxis_type,
                yaxis_type=yaxis_type,
            )
        return _FakeSweepResult(data=data, sweep_values=values, results=results)

    def _sweep_result_from_measurements(
        self,
        targets: Collection[str] | str | None,
        sweep_values: list[Any],
        *,
        results: list[Any] | None = None,
        title: str = "Sweep result",
        xlabel: str = "Sweep value",
        ylabel: str = "Measured signal",
        xaxis_type: str = "linear",
        yaxis_type: str = "linear",
    ) -> _FakeSweepResult:
        import numpy as np

        labels = self._target_labels(targets)
        values = np.asarray(sweep_values)
        data = {}
        for target in labels:
            response = np.asarray(
                [self._measurement_signal(result, target) for result in (results or [])],
                dtype=complex,
            )
            data[target] = _FakeSweepTargetData(
                target,
                values,
                response,
                title=title,
                xlabel=xlabel,
                ylabel=ylabel,
                xaxis_type=xaxis_type,
                yaxis_type=yaxis_type,
            )
        return _FakeSweepResult(data=data, sweep_values=values, results=results)

    @staticmethod
    def _measurement_signal(result: Any, target: str) -> complex:
        import numpy as np

        target_data = getattr(result, "data", {}).get(target)
        if target_data is None:
            return complex(np.nan, np.nan)
        kerneled = np.asarray(getattr(target_data, "kerneled", []), dtype=complex)
        if kerneled.size:
            return complex(np.mean(kerneled))
        captures = getattr(target_data, "data", [])
        if captures:
            capture_data = np.asarray(getattr(captures[0], "data", []), dtype=complex)
            if capture_data.size:
                return complex(np.mean(capture_data))
        return complex(np.nan, np.nan)

    def _measurement_targets(
        self,
        targets: Collection[str] | str | None,
        schedule: Any | None = None,
    ) -> list[str]:
        if targets is not None:
            return self._target_labels(targets)
        if schedule is not None:
            return self._tomography_targets(schedule)
        return self._target_labels(None)

    def _repeat_sequence_targets(self, sequence: Any) -> list[str]:
        if isinstance(sequence, Mapping):
            return [str(target) for target in sequence]
        return self._tomography_targets(sequence)

    def _simulate_measure_result(
        self,
        schedule: Any,
        *,
        targets: Collection[str] | str | None,
        shots: int,
        mode: str | None,
        initial_state: Mapping[str, str] | None,
        n_samples: int | None,
        include_decoherence: bool,
    ) -> _FakeMeasureResult:
        import numpy as np

        try:
            from qxsimulator import QuantumSimulator
        except ImportError as exc:
            raise ImportError(
                "FakeExperiment simulator execution requires qxsimulator to be installed."
            ) from exc
        labels = self._target_labels(targets)
        materialized = materialize_pulse_schedule_for_simulation(
            self._annotate_schedule_metadata(schedule)
        )
        pulse_ranges = (
            materialized.get_pulse_ranges() if hasattr(materialized, "get_pulse_ranges") else {}
        )
        has_active_pulse = any(
            pulse_range.start != pulse_range.stop
            for ranges in pulse_ranges.values()
            for pulse_range in ranges
        )
        if not has_active_pulse:
            return self._measurement_result_from_initial_state(
                labels,
                initial_state=initial_state,
                shots=shots,
                mode=mode,
            )
        initial = {label: "0" for label in self.qubit_labels}
        if initial_state:
            initial.update(initial_state)
        result = QuantumSimulator(self._qx_system(include_decoherence=include_decoherence)).mesolve(
            materialized,
            initial_state=initial,
            n_samples=n_samples or 2,
        )
        data = {}
        rng = np.random.default_rng(2027)
        for target in labels:
            populations = np.real(result._get_population(result.get_substates(target)[-1]))
            p1 = float(populations[1]) if len(populations) > 1 else 0.0
            center = self._population_to_iq(p1)
            if mode == "single":
                states = rng.random(shots) < p1
                endpoints = np.where(states, 0.5 - 0.5j, 0.5 + 0.5j)
                noise = 0.02 * (rng.normal(size=shots) + 1j * rng.normal(size=shots))
                kerneled = np.asarray(endpoints + noise, dtype=complex)
            else:
                kerneled = np.asarray([center], dtype=complex)
            captures = [
                SimpleNamespace(
                    data=np.asarray([center], dtype=complex),
                    kerneled=kerneled,
                    populations=populations,
                )
            ]
            data[target] = _FakeTargetMeasurement(kerneled=kerneled, data=captures)
        return _FakeMeasureResult(data, mode=mode)

    def _measurement_result_from_initial_state(
        self,
        targets: Collection[str] | str | None,
        *,
        initial_state: Mapping[str, str] | None,
        shots: int,
        mode: str | None,
    ) -> _FakeMeasureResult:
        import numpy as np

        labels = self._target_labels(targets)
        initial = {label: "0" for label in labels}
        if initial_state:
            initial.update({str(key): str(value) for key, value in initial_state.items()})
        data = {}
        for index, target in enumerate(labels):
            p1 = 1.0 if initial.get(target, "0") in {"1", "e"} else 0.0
            center = self._population_to_iq(p1)
            if mode == "single":
                rng = np.random.default_rng(3000 + index)
                states = rng.random(shots) < p1
                endpoints = np.where(states, 0.5 - 0.5j, 0.5 + 0.5j)
                noise = 0.02 * (rng.normal(size=shots) + 1j * rng.normal(size=shots))
                kerneled = np.asarray(endpoints + noise, dtype=complex)
            else:
                kerneled = np.asarray([center], dtype=complex)
            captures = [
                SimpleNamespace(
                    data=np.asarray([center], dtype=complex),
                    kerneled=kerneled,
                    populations=np.asarray([1.0 - p1, p1], dtype=float),
                )
            ]
            data[target] = _FakeTargetMeasurement(kerneled=kerneled, data=captures)
        return _FakeMeasureResult(data, mode=mode)

    def _measurement_result_to_probabilities(
        self,
        measurement: _FakeMeasureResult,
        *,
        shots: int,
    ) -> Any:
        probabilities = {}
        bits = []
        for target, target_data in measurement.data.items():
            signal = self._measurement_signal(measurement, target)
            p1 = self._iq_to_population(signal)
            probabilities[target] = {"0": 1.0 - p1, "1": p1}
            bits.append("1" if p1 >= 0.5 else "0")
        return self._result(
            data={
                "probabilities": probabilities,
                "counts": {"".join(bits): shots},
                "targets": list(measurement.data),
                "shots": shots,
            }
        )

    @staticmethod
    def _population_to_iq(p1: float) -> complex:
        p1 = min(1.0, max(0.0, float(p1)))
        return 0.5 + 0.5j * (1.0 - 2.0 * p1)

    @staticmethod
    def _iq_to_population(value: complex) -> float:
        return min(1.0, max(0.0, float((1.0 - 2.0 * value.imag) * 0.5)))

    def _fake_ndsweep_result(
        self,
        sweep_points: Mapping[str, Collection[Any]],
        sweep_axes: tuple[str, ...] | list[str] | None,
        *,
        targets: Collection[str] | str | None = None,
    ) -> _FakeSweepResult:
        import itertools
        import numpy as np

        axes = tuple(sweep_axes or sweep_points.keys())
        values_by_axis = {axis: list(sweep_points[axis]) for axis in axes}
        shape = tuple(len(values_by_axis[axis]) for axis in axes)
        flat_points = [
            dict(zip(axes, values, strict=True))
            for values in itertools.product(*(values_by_axis[axis] for axis in axes))
        ]
        labels = self._target_labels(targets)
        data = {target: [np.zeros(shape, dtype=complex)] for target in labels}
        return _FakeSweepResult(
            data=data,
            results=[self._fake_measure_result(labels) for _ in flat_points],
            shape=shape,
            sweep_points=flat_points,
        )

    def resolve_read_label(self, target: str, allow_legacy: bool = False) -> str:
        return f"R{target}"

    def get_target(self, label: str) -> Any:
        from types import SimpleNamespace

        if label in self.qubit_labels:
            index = self.qubit_labels.index(label)
            return SimpleNamespace(
                label=label,
                frequency=self.qubit_frequencies[index],
                object=SimpleNamespace(label=label),
            )
        if "-" in label:
            control, target = label.split("-", 1)
            target_index = self.qubit_labels.index(target)
            return SimpleNamespace(
                label=label,
                frequency=self.qubit_frequencies[target_index],
                object=SimpleNamespace(label=control),
            )
        if label.startswith("R") and label[1:] in self.qubit_labels:
            index = self.qubit_labels.index(label[1:])
            return SimpleNamespace(
                label=label,
                frequency=self.readout_frequencies[index],
                object=SimpleNamespace(label=label),
            )
        raise ValueError(label)

    def repeat_sequence(
        self,
        sequence: Any,
        *,
        repetitions: int = 20,
        initial_state: Mapping[str, str] | None = None,
        initial_states: Mapping[str, str] | None = None,
        n_shots: int | None = None,
        shot_interval: float | None = None,
        plot: bool | None = True,
        _simulator: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        """Repeat a pulse or pulse schedule and return a QUBEX-style result."""
        import numpy as np

        if plot is None:
            plot = True
        initial = dict(initial_states or initial_state or {})
        if isinstance(sequence, Mapping) and not sequence:
            raise ValueError(
                "repeat_sequence received an empty pulse mapping. "
                "Run calibrate_hpi_pulse(...) or pass a mapping like {Q0: pulse}."
            )
        target_labels = self._repeat_sequence_targets(sequence)
        use_simulator = kwargs.pop("use_simulator", _simulator is not None)
        if not use_simulator and kwargs.get("simulate") is not True:
            result = self._repeat_sequence_fast_result(
                sequence,
                target_labels=target_labels,
                repetitions=repetitions,
                initial_state=initial,
            )
            if plot:
                result.plot(normalize=True)
            return result

        def repeated_sequence(repetition_count: int) -> Any:
            import qubex as qx

            if isinstance(sequence, Mapping):
                with qx.PulseSchedule(list(sequence)) as schedule:
                    for target, pulse in sequence.items():
                        schedule.add(target, pulse.repeated(int(repetition_count)))
                return schedule
            if hasattr(sequence, "repeated"):
                return sequence.repeated(int(repetition_count))
            raise TypeError("Invalid sequence.")

        result = self.sweep_parameter(
            sequence=repeated_sequence,
            sweep_range=np.arange(repetitions + 1),
            targets=target_labels,
            initial_state=initial,
            n_shots=n_shots,
            shot_interval=shot_interval,
            plot=False,
            xlabel="Number of repetitions",
            use_simulator=use_simulator,
            **kwargs,
        )
        for value in result.data.values():
            value.title = "Repeat sequence"
            value.ylabel = "Normalized signal"
        if plot:
            result.plot(normalize=True)
        return result

    def _repeat_sequence_fast_result(
        self,
        sequence: Any,
        *,
        target_labels: Collection[str],
        repetitions: int,
        initial_state: Mapping[str, str],
    ) -> _FakeSweepResult:
        import numpy as np

        values = np.arange(repetitions + 1)
        data = {}
        for target in target_labels:
            angle = self._repeat_sequence_rotation_angle(sequence, target)
            sign = -1.0 if str(initial_state.get(target, "0")) in {"1", "e"} else 1.0
            normalized = sign * np.cos(values * angle)
            response = 0.5 + 0.5j * normalized
            data[target] = _FakeSweepTargetData(
                target,
                values,
                response,
                title="Repeat sequence",
                xlabel="Number of repetitions",
                ylabel="Normalized signal",
            )
        return _FakeSweepResult(data=data, sweep_values=values, results=[])

    def _repeat_sequence_rotation_angle(self, sequence: Any, target: str) -> float:
        import numpy as np

        pulse = sequence.get(target) if isinstance(sequence, Mapping) else sequence
        amplitude = getattr(pulse, "amplitude", None)
        if amplitude is not None:
            try:
                return float(abs(amplitude)) * np.pi
            except (TypeError, ValueError):
                pass
        return 0.5 * np.pi

    def pulse_tomography(
        self,
        sequence: Any,
        *,
        initial_state: Mapping[str, str] | None = None,
        n_samples: int | None = None,
        plot: bool | None = True,
        **_: Any,
    ) -> Any:
        """Run simulated pulse tomography with the QUBEX experiment API shape."""
        try:
            (
                np,
                _pd,
                qx,
                _qt,
                Result,
                _StateClassifierGMM,
                _Control,
                QuantumSimulator,
            ) = _simulation_dependencies()
        except ImportError:
            return self._lightweight_pulse_tomography(sequence, initial_state=initial_state)
        initial = {label: "0" for label in self.qubit_labels}
        if initial_state:
            initial.update(initial_state)
        result = QuantumSimulator(self._qx_system()).mesolve(
            self._annotate_schedule_metadata(sequence),
            initial_state=initial,
            n_samples=n_samples or 100,
        )
        data = {
            target: result.get_bloch_vectors(target)
            for target in self._tomography_targets(sequence)
        }
        figures = {}
        if plot:
            for target, vectors in data.items():
                fig = qx.viz.make_figure()
                for axis, values in zip(("X", "Y", "Z"), np.asarray(vectors).T, strict=True):
                    fig.add_scatter(x=result.times, y=values, mode="lines", name=axis)
                fig.update_layout(
                    title=f"State evolution : {target}",
                    xaxis_title="Time [ns]",
                    yaxis_title="Bloch vector",
                    yaxis_range=[-1.1, 1.1],
                )
                figures[target] = fig
        return Result(data=data, figures=figures, figure=next(iter(figures.values()), None))

    def measure_bell_state(
        self,
        control_qubit: str,
        target_qubit: str,
        *,
        control_basis: str | None = None,
        target_basis: str | None = None,
        zx90: Any | None = None,
        plot: bool | None = True,
        **_: Any,
    ) -> Any:
        """Measure a simulated Bell state in the requested Pauli basis."""
        try:
            (
                np,
                _pd,
                qx,
                _qt,
                Result,
                _StateClassifierGMM,
                _Control,
                QuantumSimulator,
            ) = _simulation_dependencies()
        except ImportError:
            return self._lightweight_bell_state(
                control_basis=control_basis, target_basis=target_basis
            )
        control_basis = control_basis or "Z"
        target_basis = target_basis or "Z"
        schedule = self._bell_measurement_schedule(
            control_qubit,
            target_qubit,
            control_basis=control_basis,
            target_basis=target_basis,
            zx90=zx90,
        )
        result = QuantumSimulator(self._qx_system()).mesolve(
            self._annotate_schedule_metadata(schedule),
            initial_state={control_qubit: "0", target_qubit: "0"},
            n_samples=2,
        )
        probabilities = self._computational_probabilities(result)
        raw = np.array([probabilities[label] for label in ("00", "01", "10", "11")])
        figure = None
        if plot:
            figure = qx.viz.make_figure()
            labels = ["|00>", "|01>", "|10>", "|11>"]
            figure.add_bar(x=labels, y=raw, name="Raw")
            figure.add_bar(x=labels, y=raw, name="Mitigated")
            figure.update_layout(
                title=f"Bell state measurement: {control_qubit}-{target_qubit}",
                xaxis_title=f"State ({control_basis}{target_basis} basis)",
                yaxis_title="Probability",
                barmode="group",
                yaxis_range=[0, 1],
            )
        return Result(
            data={
                "raw": raw,
                "mitigated": raw.copy(),
                "probabilities": probabilities,
                "basis": f"{control_basis}{target_basis}",
            },
            figure=figure,
        )

    def bell_state_tomography(
        self,
        control_qubit: str,
        target_qubit: str,
        *,
        readout_mitigation: bool | None = True,
        zx90: Any | None = None,
        plot: bool | None = True,
        mle_fit: bool | None = False,
        **_: Any,
    ) -> Any:
        """Perform lightweight Bell-state tomography from simulated basis probabilities."""
        try:
            (
                np,
                _pd,
                qx,
                _qt,
                Result,
                _StateClassifierGMM,
                _Control,
                _QuantumSimulator,
            ) = _simulation_dependencies()
        except ImportError:
            import numpy as np

            rho = np.array(
                [
                    [0.5, 0.0, 0.0, 0.5],
                    [0.0, 0.0, 0.0, 0.0],
                    [0.0, 0.0, 0.0, 0.0],
                    [0.5, 0.0, 0.0, 0.5],
                ],
                dtype=complex,
            )
            return self._result(
                data={
                    "density_matrix": rho,
                    "fidelity": 1.0,
                    "mle_fit": bool(mle_fit),
                }
            )
        probabilities = {}
        for control_basis in ("X", "Y", "Z"):
            for target_basis in ("X", "Y", "Z"):
                result = self.measure_bell_state(
                    control_qubit,
                    target_qubit,
                    control_basis=control_basis,
                    target_basis=target_basis,
                    zx90=zx90,
                    plot=False,
                )
                probabilities[f"{control_basis}{target_basis}"] = (
                    result["mitigated"] if readout_mitigation else result["raw"]
                )

        paulis = {
            "I": np.array([[1, 0], [0, 1]], dtype=complex),
            "X": np.array([[0, 1], [1, 0]], dtype=complex),
            "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
            "Z": np.array([[1, 0], [0, -1]], dtype=complex),
        }
        expected_values = {}
        rho = np.zeros((4, 4), dtype=complex)
        for control_basis, control_pauli in paulis.items():
            for target_basis, target_pauli in paulis.items():
                basis = f"{control_basis}{target_basis}"
                if basis == "II":
                    p = probabilities["ZZ"]
                    expectation = p[0] + p[1] + p[2] + p[3]
                elif control_basis == "I":
                    p = probabilities[f"Z{target_basis}"]
                    expectation = p[0] - p[1] + p[2] - p[3]
                elif target_basis == "I":
                    p = probabilities[f"{control_basis}Z"]
                    expectation = p[0] + p[1] - p[2] - p[3]
                else:
                    p = probabilities[basis]
                    expectation = p[0] - p[1] - p[2] + p[3]
                expected_values[basis] = float(np.real(expectation))
                rho += expectation * np.kron(control_pauli, target_pauli)
        rho = rho / 4
        bell = np.array([1, 0, 0, 1], dtype=complex) / np.sqrt(2)
        fidelity = float(np.real(np.conj(bell) @ rho @ bell))
        figure = None
        if plot:
            figure = qx.viz.make_figure()
            figure.add_heatmap(
                z=np.real(rho),
                x=["00", "01", "10", "11"],
                y=["00", "01", "10", "11"],
                colorscale="RdBu",
                zmid=0,
            )
            figure.update_layout(
                title=f"Bell state tomography: {control_qubit}-{target_qubit} (F={fidelity:.4f})",
                width=600,
                height=420,
            )
        return Result(
            data={
                "probabilities": probabilities,
                "expected_values": expected_values,
                "density_matrix": rho,
                "fidelity": fidelity,
                "mle_fit": bool(mle_fit),
            },
            figure=figure,
        )

    def zx90_gate_fidelity(
        self,
        control_qubit: str,
        target_qubit: str,
        *,
        zx90: Any | None = None,
        include_decoherence: bool = False,
        **_: Any,
    ) -> Any:
        """Compute qxsimulator average gate fidelity for the calibrated ZX90 pulse."""
        np, _pd, _qx, qt, Result, _StateClassifierGMM, _Control, QuantumSimulator = (
            _simulation_dependencies()
        )
        target_unitary = qt.Qobj(
            [
                [1, -1j, 0, 0],
                [-1j, 1, 0, 0],
                [0, 0, 1, 1j],
                [0, 0, 1j, 1],
            ]
        ) / np.sqrt(2)
        target_unitary.dims = [[2, 2], [2, 2]]
        fidelity = QuantumSimulator(
            self._qx_system(include_decoherence=include_decoherence)
        ).gate_fidelity(
            controls=self._annotate_schedule_metadata(
                zx90 or self.zx90(control_qubit, target_qubit)
            ),
            target_unitary=target_unitary,
        )
        self.two_qubit_fidelity = float(fidelity)
        return Result(
            data={
                "gate": "zx90",
                "control": control_qubit,
                "target": target_qubit,
                "fidelity": float(fidelity),
                "include_decoherence": include_decoherence,
            }
        )

    def cx_gate_fidelity(
        self,
        control_qubit: str,
        target_qubit: str,
        *,
        include_decoherence: bool = False,
        **_: Any,
    ) -> Any:
        """Compute qxsimulator average gate fidelity for the synthesized Qiskit CX."""
        _np, _pd, _qx, qt, Result, _StateClassifierGMM, _Control, QuantumSimulator = (
            _simulation_dependencies()
        )
        fidelity = QuantumSimulator(
            self._qx_system(include_decoherence=include_decoherence)
        ).gate_fidelity(
            controls=materialize_pulse_schedule_for_simulation(
                self._annotate_schedule_metadata(self.cx(control_qubit, target_qubit))
            ),
            target_unitary=self._cx_target_unitary(qt),
        )
        return Result(
            data={
                "gate": "cx",
                "control": control_qubit,
                "target": target_qubit,
                "fidelity": float(fidelity),
                "include_decoherence": include_decoherence,
            }
        )

    def calibrate_cx_frame(
        self,
        control_qubit: str,
        target_qubit: str,
        *,
        phase_grid: Any | None = None,
        include_decoherence: bool = False,
        **_: Any,
    ) -> Any:
        """Estimate local-Z frame dressing required by the synthesized CX pulse."""
        np, _pd, _qx, qt, Result, _StateClassifierGMM, _Control, QuantumSimulator = (
            _simulation_dependencies()
        )
        if phase_grid is None:
            phase_grid = np.linspace(-np.pi, np.pi, 25)
        else:
            phase_grid = np.asarray(phase_grid, dtype=float)

        simulator = QuantumSimulator(self._qx_system(include_decoherence=include_decoherence))
        superop = simulator.propagator(
            materialize_pulse_schedule_for_simulation(
                self._annotate_schedule_metadata(self.cx(control_qubit, target_qubit))
            )
        )
        superop = simulator.system.truncate_superoperator(superop)
        cx_unitary = self._cx_target_unitary(qt)
        base_fidelity = float(qt.average_gate_fidelity(superop, cx_unitary))

        best_fidelity = base_fidelity
        best_control_phase = 0.0
        best_target_phase = 0.0
        for control_phase in phase_grid:
            for target_phase in phase_grid:
                dressed = self._dressed_cx_target_unitary(
                    qt,
                    np,
                    float(control_phase),
                    float(target_phase),
                )
                fidelity = float(qt.average_gate_fidelity(superop, dressed))
                if fidelity > best_fidelity:
                    best_fidelity = fidelity
                    best_control_phase = float(control_phase)
                    best_target_phase = float(target_phase)

        frame_param = {
            "control": control_qubit,
            "target": target_qubit,
            "base_fidelity": base_fidelity,
            "dressed_fidelity": best_fidelity,
            "post_control_z": best_control_phase,
            "post_target_z": best_target_phase,
            "include_decoherence": include_decoherence,
        }
        self.cx_frame_params[f"{control_qubit}-{target_qubit}"] = frame_param
        return Result(data=frame_param)

    def measure_state_distribution(
        self,
        targets: Collection[str] | str | None = None,
        *,
        n_states: int = 2,
        n_shots: int = 10_000,
        **_: Any,
    ) -> Any:
        """Generate synthetic IQ distributions for classifier calibration."""
        try:
            (
                np,
                _pd,
                _qx,
                _qt,
                Result,
                _StateClassifierGMM,
                _Control,
                _QuantumSimulator,
            ) = _simulation_dependencies()
        except ImportError:
            return self._lightweight_state_distribution(targets, n_states=n_states, n_shots=n_shots)
        rng = np.random.default_rng(7)
        centers = {0: 0.10 + 0.02j, 1: 0.86 + 0.34j, 2: 1.14 - 0.20j}
        sigma = 0.16
        target_labels = self._target_labels(targets)
        distributions = []
        for state in range(n_states):
            shot_map = {}
            for target in target_labels:
                sampled_states = np.full(n_shots, state)
                noise = sigma * (rng.normal(size=n_shots) + 1j * rng.normal(size=n_shots))
                shot_map[target] = np.array([centers[int(s)] for s in sampled_states]) + noise
            distributions.append(shot_map)
        return Result(data={"distributions": distributions})

    def build_classifier(
        self,
        targets: Collection[str] | str | None = None,
        *,
        n_states: int = 2,
        n_shots: int = 10_000,
        plot: bool | None = True,
        **_: Any,
    ) -> Any:
        """Build synthetic state classifiers with the QUBEX experiment API shape."""
        try:
            (
                np,
                _pd,
                qx,
                _qt,
                Result,
                StateClassifierGMM,
                _Control,
                _QuantumSimulator,
            ) = _simulation_dependencies()
        except ImportError:
            distributions = self._lightweight_state_distribution(
                targets,
                n_states=n_states,
                n_shots=n_shots,
            )["distributions"]
            classifiers = {
                target: SimpleNamespace(
                    target=target,
                    n_states=n_states,
                    classify=lambda values, _target=target: [0 for _ in values],
                    plot=lambda *args, **kwargs: None,
                )
                for target in self._target_labels(targets)
            }
            self.classifiers.update(classifiers)
            return self._result(
                data={
                    "classifiers": classifiers,
                    "distributions": distributions,
                    "fidelities": {target: 1.0 for target in self._target_labels(targets)},
                }
            )
        target_labels = self._target_labels(targets)
        distributions = self.measure_state_distribution(
            target_labels,
            n_states=n_states,
            n_shots=n_shots,
        )["distributions"]
        data = {
            target: {state: distributions[state][target] for state in range(n_states)}
            for target in target_labels
        }
        classifiers = {
            target: StateClassifierGMM.fit(data[target], phase=0.0) for target in target_labels
        }
        classified = {}
        fidelities = {}
        figures = {}
        for target in target_labels:
            classified[target] = []
            for state in range(n_states):
                predicted = classifiers[target].predict(data[target][state])
                counts = np.bincount(predicted, minlength=classifiers[target].n_states)
                classified[target].append(
                    {label: int(counts[label]) for label in range(len(counts))}
                )
                if plot:
                    fig = qx.viz.make_classification_figure(
                        target=target,
                        data=data[target][state],
                        labels=predicted,
                        centers=classifiers[target].centers,
                        stddevs=classifiers[target].stddevs,
                    )
                    fig.update_layout(title=f"{target} prepared as |{state}>")
                    figures[f"{target}:{state}"] = fig
            fidelities[target] = [
                classified[target][state][state] / sum(classified[target][state].values())
                for state in range(n_states)
            ]
            self.classifiers[target] = classifiers[target]
            self.readout_assignment_errors[target] = 1.0 - float(np.mean(fidelities[target]))
        return Result(
            data={
                "data": data,
                "classifiers": classifiers,
                "classified": classified,
                "readout_fidelities": fidelities,
                "average_readout_fidelity": {
                    target: float(np.mean(fidelities[target])) for target in target_labels
                },
            },
            figures=figures,
        )

    @property
    def clifford_generator(self) -> Any:
        """Return QUBEX's Clifford generator used by RB sequence builders."""
        from qubex.clifford import CliffordGenerator

        if self._clifford_generator is None:
            self._clifford_generator = CliffordGenerator()
        return self._clifford_generator

    @property
    def clifford(self) -> dict[str, Any]:
        """Return the QUBEX Clifford dictionary."""
        return self.clifford_generator.cliffords

    def rb_sequence(
        self,
        target: str,
        *,
        n: int,
        x90: Any | Mapping[str, Any] | None = None,
        zx90: Any | None = None,
        interleaved_waveform: Any | None = None,
        interleaved_clifford: Any | None = None,
        seed: int | None = None,
    ) -> Any:
        """Build a QUBEX-style randomized benchmarking pulse schedule."""
        if "-" in target:
            if x90 is not None and not isinstance(x90, Mapping):
                raise ValueError("x90 must be a mapping for 2Q RB.")
            return self._rb_sequence_2q(
                target,
                n=n,
                x90=x90,
                zx90=zx90,
                interleaved_waveform=interleaved_waveform,
                interleaved_clifford=interleaved_clifford,
                seed=seed,
            )
        if isinstance(x90, Mapping):
            x90 = x90.get(target)
        return self._rb_sequence_1q(
            target,
            n=n,
            x90=x90,
            interleaved_waveform=interleaved_waveform,
            interleaved_clifford=interleaved_clifford,
            seed=seed,
        )

    def randomized_benchmarking(
        self,
        targets: Collection[str] | str,
        *,
        n_cliffords_range: Any | None = None,
        n_trials: int | None = None,
        seeds: Any | None = None,
        max_n_cliffords: int | None = None,
        x90: Mapping[str, Any] | None = None,
        zx90: Mapping[str, Any] | None = None,
        plot: bool | None = True,
        include_decoherence: bool = False,
        **_: Any,
    ) -> Any:
        """Run pulse-schedule RB through qxsimulator with the QUBEX API shape."""
        try:
            return self._rb_experiment(
                targets,
                n_cliffords_range=n_cliffords_range,
                n_trials=n_trials,
                seeds=seeds,
                max_n_cliffords=max_n_cliffords,
                x90=x90,
                zx90=zx90,
                interleaved_clifford=None,
                interleaved_waveform=None,
                plot=plot,
                include_decoherence=include_decoherence,
            )
        except ImportError:
            return self._lightweight_rb_result(
                targets,
                n_cliffords_range=n_cliffords_range,
                max_n_cliffords=max_n_cliffords,
            )

    def interleaved_randomized_benchmarking(
        self,
        targets: Collection[str] | str,
        *,
        interleaved_clifford: str | Any,
        interleaved_waveform: Mapping[str, Any] | None = None,
        n_cliffords_range: Any | None = None,
        n_trials: int | None = None,
        seeds: Any | None = None,
        max_n_cliffords: int | None = None,
        x90: Mapping[str, Any] | None = None,
        zx90: Mapping[str, Any] | None = None,
        plot: bool | None = True,
        include_decoherence: bool = False,
        **_: Any,
    ) -> Any:
        """Run interleaved pulse-schedule RB through qxsimulator."""
        try:
            if isinstance(interleaved_clifford, str):
                interleaved_clifford = self.clifford[interleaved_clifford]
            return self._rb_experiment(
                targets,
                n_cliffords_range=n_cliffords_range,
                n_trials=n_trials,
                seeds=seeds,
                max_n_cliffords=max_n_cliffords,
                x90=x90,
                zx90=zx90,
                interleaved_clifford=interleaved_clifford,
                interleaved_waveform=interleaved_waveform,
                plot=plot,
                include_decoherence=include_decoherence,
            )
        except ImportError:
            return self._lightweight_rb_result(
                targets,
                n_cliffords_range=n_cliffords_range,
                max_n_cliffords=max_n_cliffords,
                interleaved_clifford=interleaved_clifford,
            )

    def check_waveform(self, waveform: Any | None = None, **_: Any) -> Any:
        return self._result(data={"waveform": waveform, "ok": True})

    def check_rabi(
        self,
        targets: Collection[str] | str | None = None,
        *,
        time_range: Any | None = None,
        store_params: bool | None = None,
        rabi_level: str | None = None,
        plot: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        if rabi_level is None:
            rabi_level = "ge"
        labels = self._target_labels(targets)
        amplitudes = {target: 1.0 for target in labels}
        if rabi_level == "ef":
            return self.ef_rabi_experiment(
                amplitudes=amplitudes,
                time_range=time_range,
                store_params=store_params,
                plot=plot,
                **kwargs,
            )
        return self.rabi_experiment(
            amplitudes=amplitudes,
            time_range=time_range,
            store_params=store_params,
            plot=plot,
            **kwargs,
        )

    def obtain_rabi_params(
        self,
        targets: Collection[str] | str | None = None,
        *,
        time_range: Any | None = None,
        amplitudes: dict[str, float] | None = None,
        frequencies: dict[str, float] | None = None,
        is_damped: bool | None = None,
        fit_threshold: float | None = None,
        plot: bool | None = None,
        store_params: bool | None = None,
        simultaneous: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        del frequencies, is_damped, fit_threshold, simultaneous
        labels = self._target_labels(targets)
        amplitudes = amplitudes or {target: 1.0 for target in labels}
        return self.rabi_experiment(
            amplitudes=amplitudes,
            time_range=time_range,
            plot=plot,
            store_params=True if store_params is None else store_params,
            **kwargs,
        )

    def obtain_ef_rabi_params(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        labels = self._target_labels(targets)
        amplitudes = kwargs.pop("amplitudes", None) or {target: 1.0 for target in labels}
        return self.ef_rabi_experiment(amplitudes=amplitudes, **kwargs)

    def rabi_experiment(
        self,
        targets: Collection[str] | str | None = None,
        *,
        amplitudes: dict[str, float] | None = None,
        time_range: Any | None = None,
        ramptime: float | None = None,
        frequencies: dict[str, float] | None = None,
        detuning: float | None = None,
        is_damped: bool | None = None,
        fit_threshold: float | None = None,
        n_shots: int | None = None,
        shot_interval: float | None = None,
        plot: bool | None = None,
        store_params: bool | None = None,
        **_: Any,
    ) -> Any:
        del frequencies, detuning, is_damped, fit_threshold, n_shots, shot_interval
        if plot is None:
            plot = True
        labels = self._target_labels(targets) if amplitudes is None else list(amplitudes)
        amplitudes = amplitudes or {target: 1.0 for target in labels}
        result = self._rabi_result(
            amplitudes=amplitudes,
            time_range=time_range,
            ramptime=ramptime,
            store_params=bool(store_params),
            transition="ge",
        )
        if plot:
            result.plot()
        return result

    def ef_rabi_experiment(
        self,
        targets: Collection[str] | str | None = None,
        *,
        amplitudes: dict[str, float] | None = None,
        time_range: Any | None = None,
        ramptime: float | None = None,
        frequencies: dict[str, float] | None = None,
        detuning: float | None = None,
        is_damped: bool | None = None,
        n_shots: int | None = None,
        shot_interval: float | None = None,
        plot: bool | None = None,
        store_params: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        del frequencies, detuning, is_damped, n_shots, shot_interval, kwargs
        if plot is None:
            plot = True
        labels = self._target_labels(targets) if amplitudes is None else list(amplitudes)
        amplitudes = amplitudes or {target: 1.0 for target in labels}
        result = self._rabi_result(
            amplitudes=amplitudes,
            time_range=time_range,
            ramptime=ramptime,
            store_params=bool(store_params),
            transition="ef",
        )
        if plot:
            result.plot()
        return result

    def state_tomography(self, sequence: Any, **kwargs: Any) -> Any:
        return self.pulse_tomography(sequence, **kwargs)

    def state_evolution_tomography(self, sequence: Any, **kwargs: Any) -> Any:
        return self.pulse_tomography(sequence, **kwargs)

    def measure_population(self, sequence: Any, **kwargs: Any) -> Any:
        tomography = self.pulse_tomography(sequence, plot=False, **kwargs)
        data = {}
        for target, vectors in tomography["data"].items():
            data[target] = (1.0 - vectors[-1][2]) / 2.0
        return self._result(data=data)

    def measure_population_dynamics(self, sequence: Any, **kwargs: Any) -> Any:
        return self.pulse_tomography(sequence, **kwargs)

    def measure_readout_snr(
        self,
        targets: Collection[str] | str | None = None,
        **_: Any,
    ) -> Any:
        return self._result(data={target: 8.0 for target in self._target_labels(targets)})

    def sweep_readout_amplitude(self, *args: Any, **kwargs: Any) -> Any:
        return self._sweep_stub("readout_amplitude", *args, **kwargs)

    def sweep_readout_duration(self, *args: Any, **kwargs: Any) -> Any:
        return self._sweep_stub("readout_duration", *args, **kwargs)

    def chevron_pattern(self, *args: Any, **kwargs: Any) -> Any:
        return self._chevron_pattern_result(*args, **kwargs)

    def obtain_freq_rabi_relation(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"slope": 1.0, "intercept": 0.0})

    def obtain_ampl_rabi_relation(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"slope": 1.0, "intercept": 0.0})

    def calibrate_control_frequency(
        self,
        targets: Collection[str] | str | None = None,
        **_: Any,
    ) -> Any:
        return self._result(
            data={
                target: self.qubit_frequencies[self.qubit_labels.index(target)]
                for target in self._target_labels(targets)
            }
        )

    def calibrate_ef_control_frequency(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.calibrate_control_frequency(targets, **kwargs)

    def calibrate_readout_frequency(
        self,
        targets: Collection[str] | str | None = None,
        **_: Any,
    ) -> Any:
        return self._result(
            data={
                target: self.readout_frequencies[self.qubit_labels.index(target)]
                for target in self._target_labels(targets)
            }
        )

    def t1_experiment(
        self,
        targets: Collection[str] | str | None = None,
        *,
        time_range: Any | None = None,
        plot: bool | None = None,
        xaxis_type: str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._coherence_result(
            targets,
            time_range=time_range,
            experiment="t1",
            plot=True if plot is None else plot,
            xaxis_type=xaxis_type or "log",
            shots=kwargs.get("shots"),
            interval=kwargs.get("interval"),
            use_simulator=bool(kwargs.get("use_simulator", False)),
        )

    def t2_experiment(
        self,
        targets: Collection[str] | str | None = None,
        *,
        time_range: Any | None = None,
        n_cpmg: int | None = None,
        plot: bool | None = None,
        xaxis_type: str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._coherence_result(
            targets,
            time_range=time_range,
            experiment="t2",
            plot=True if plot is None else plot,
            xaxis_type=xaxis_type or "log",
            n_cpmg=n_cpmg,
            shots=kwargs.get("shots"),
            interval=kwargs.get("interval"),
            use_simulator=bool(kwargs.get("use_simulator", False)),
        )

    def ramsey_experiment(
        self,
        targets: Collection[str] | str | None = None,
        *,
        time_range: Any | None = None,
        detuning: float | None = None,
        second_rotation_axis: str | None = None,
        spectator_state: str | None = None,
        plot: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        return self._coherence_result(
            targets,
            time_range=time_range,
            experiment="ramsey",
            detuning=0.001 if detuning is None else float(detuning),
            second_rotation_axis=(second_rotation_axis or "Y"),
            spectator_state=spectator_state or "0",
            plot=True if plot is None else plot,
            xaxis_type="linear",
            shots=kwargs.get("shots"),
            interval=kwargs.get("interval"),
            use_simulator=bool(kwargs.get("use_simulator", False)),
        )

    def obtain_effective_control_frequency(self, *args: Any, **kwargs: Any) -> Any:
        return self.calibrate_control_frequency(*args, **kwargs)

    def jazz_experiment(self, *args: Any, **kwargs: Any) -> Any:
        return self._sweep_stub("jazz", *args, **kwargs)

    def obtain_coupling_strength(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"coupling_strength": self.coupling_strength})

    def scan_resonator_frequencies(
        self,
        target: str | None = None,
        *,
        frequency_range: Any | None = None,
        **_: Any,
    ) -> Any:
        import numpy as np

        del target
        if frequency_range is None:
            values = np.asarray(self.readout_frequencies)
        else:
            values = np.asarray(frequency_range, dtype=float)
        if len(values) >= 4:
            indices = np.linspace(0, len(values) - 1, 4, dtype=int)
            peaks = [float(values[index]) for index in indices]
        else:
            peaks = list(map(float, self.readout_frequencies[:4]))
        return self._result(
            data={
                "frequency_range": values,
                "response": np.zeros_like(values, dtype=float),
                "peaks": peaks,
            }
        )

    def resonator_spectroscopy(self, *args: Any, **kwargs: Any) -> Any:
        return self.scan_resonator_frequencies(*args, **kwargs)

    def measure_reflection_coefficient(self, target: str, **_: Any) -> Any:
        index = self.qubit_labels.index(target)
        return self._result(data={"target": target, "f_r": self.readout_frequencies[index]})

    def scan_qubit_frequencies(
        self,
        target: str,
        *,
        frequency_range: Any | None = None,
        **_: Any,
    ) -> Any:
        import numpy as np

        index = self.qubit_labels.index(target)
        values = (
            np.asarray(frequency_range, dtype=float)
            if frequency_range is not None
            else np.linspace(
                self.qubit_frequencies[index] - 0.1,
                self.qubit_frequencies[index] + 0.1,
                101,
            )
        )
        return self._result(
            data={
                "target": target,
                "frequency_range": values,
                "response": np.zeros_like(values, dtype=float),
                "f_q": self.qubit_frequencies[index],
            }
        )

    def qubit_spectroscopy(self, *args: Any, **kwargs: Any) -> Any:
        return self.scan_qubit_frequencies(*args, **kwargs)

    def measure_qubit_resonance(self, target: str, **kwargs: Any) -> Any:
        return self.scan_qubit_frequencies(target, **kwargs)

    def measure_electrical_delay(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"delay": 0.0})

    def find_optimal_readout_frequency(self, target: str, **kwargs: Any) -> Any:
        return self.measure_reflection_coefficient(target, **kwargs)

    def find_optimal_readout_amplitude(self, target: str, **_: Any) -> Any:
        return self._result(data={"target": target, "readout_amplitude": 0.1})

    def characterize_1q(self, targets: Collection[str] | str | None = None, **_: Any) -> Any:
        return self._result(
            data={
                "t1": self.t1_experiment(targets),
                "t2": self.t2_experiment(targets),
                "readout_snr": self.measure_readout_snr(targets),
            }
        )

    def characterize_2q(self, targets: Collection[str] | str | None = None, **_: Any) -> Any:
        return self.calibrate_2q(targets, plot=False)

    def benchmark_1q(self, targets: Collection[str] | str | None = None, **kwargs: Any) -> Any:
        return self.randomized_benchmarking(targets or self.qubit_labels[0], **kwargs)

    def benchmark_2q(self, targets: Collection[str] | str | None = None, **kwargs: Any) -> Any:
        pair = self.get_cr_pairs(targets)[0]
        return self.randomized_benchmarking(list(pair), **kwargs)

    def purity_benchmarking(self, *args: Any, **kwargs: Any) -> Any:
        return self.randomized_benchmarking(*args, **kwargs)

    def interleaved_purity_benchmarking(self, *args: Any, **kwargs: Any) -> Any:
        return self.interleaved_randomized_benchmarking(*args, **kwargs)

    def optimize_x90(self, targets: Collection[str] | str | None = None, **kwargs: Any) -> Any:
        return self.calibrate_drag_hpi_pulse(targets, **kwargs)

    def optimize_drag_x90(
        self,
        targets: Collection[str] | str | None = None,
        **kwargs: Any,
    ) -> Any:
        return self.calibrate_drag_hpi_pulse(targets, **kwargs)

    def optimize_pulse(self, *args: Any, **kwargs: Any) -> Any:
        return self._result(data={"optimized": True})

    def optimize_zx90(self, control_qubit: str, target_qubit: str, **kwargs: Any) -> Any:
        return self.calibrate_zx90(control_qubit, target_qubit, **kwargs)

    def _rb_sequence_1q(
        self,
        target: str,
        *,
        n: int,
        x90: Any | None = None,
        interleaved_waveform: Any | None = None,
        interleaved_clifford: Any | None = None,
        seed: int | None = None,
    ) -> Any:
        np, _pd, qx, _qt, _Result, _StateClassifierGMM, _Control, _QuantumSimulator = (
            _simulation_dependencies()
        )
        x90 = x90 or self.x90(target)
        z90 = qx.pulse.VirtualZ(np.pi / 2)
        if interleaved_clifford is None:
            cliffords, inverse = self.clifford_generator.create_rb_sequences(
                n=n,
                type="1Q",
                seed=seed,
            )
        else:
            if interleaved_waveform is None:
                if interleaved_clifford.name == "X90":
                    interleaved_waveform = self.x90(target)
                elif interleaved_clifford.name == "X180":
                    interleaved_waveform = self.x180(target)
                else:
                    raise ValueError("interleaved_waveform must be provided.")
            cliffords, inverse = self.clifford_generator.create_irb_sequences(
                n=n,
                interleave=interleaved_clifford,
                type="1Q",
                seed=seed,
            )
        sequence = []

        def add_gate(gate: str) -> None:
            if gate == "X90":
                sequence.append(x90)
            elif gate == "Z90":
                sequence.append(z90)
            else:
                raise ValueError(f"Invalid 1Q Clifford gate {gate!r}.")

        for clifford in cliffords:
            for gate in clifford:
                add_gate(gate)
            if interleaved_waveform is not None:
                sequence.append(interleaved_waveform)
        for gate in inverse:
            add_gate(gate)
        with qx.PulseSchedule([target]) as schedule:
            schedule.add(target, qx.PulseArray(sequence))
        return schedule

    def _rb_sequence_2q(
        self,
        target: str,
        *,
        n: int,
        x90: Mapping[str, Any] | None = None,
        zx90: Any | None = None,
        interleaved_waveform: Any | None = None,
        interleaved_clifford: Any | None = None,
        seed: int | None = None,
    ) -> Any:
        np, _pd, qx, _qt, _Result, _StateClassifierGMM, _Control, _QuantumSimulator = (
            _simulation_dependencies()
        )
        control_qubit, target_qubit = target.split("-", 1)
        xi90 = x90.get(control_qubit) if x90 is not None else None
        ix90 = x90.get(target_qubit) if x90 is not None else None
        xi90 = xi90 or self.x90(control_qubit)
        ix90 = ix90 or self.x90(target_qubit)
        z90 = qx.pulse.VirtualZ(np.pi / 2)
        zx90 = zx90 or self.zx90(control_qubit, target_qubit)
        if interleaved_clifford is None:
            cliffords, inverse = self.clifford_generator.create_rb_sequences(
                n=n,
                type="2Q",
                seed=seed,
            )
        else:
            if interleaved_waveform is None:
                if interleaved_clifford.name == "ZX90":
                    interleaved_waveform = self.zx90(control_qubit, target_qubit)
                else:
                    raise ValueError("interleaved_waveform must be provided.")
            cliffords, inverse = self.clifford_generator.create_irb_sequences(
                n=n,
                interleave=interleaved_clifford,
                type="2Q",
                seed=seed,
            )
        with qx.PulseSchedule([control_qubit, target, target_qubit]) as schedule:

            def add_gate(gate: str) -> None:
                if gate == "XI90":
                    schedule.add(control_qubit, xi90)
                elif gate == "IX90":
                    schedule.add(target_qubit, ix90)
                elif gate == "ZI90":
                    schedule.add(control_qubit, z90)
                elif gate == "IZ90":
                    schedule.add(target_qubit, z90)
                    schedule.add(target, z90)
                elif gate == "ZX90":
                    schedule.barrier()
                    schedule.call(zx90)
                    schedule.barrier()
                else:
                    raise ValueError(f"Invalid 2Q Clifford gate {gate!r}.")

            for clifford in cliffords:
                for gate in clifford:
                    add_gate(gate)
                if interleaved_waveform is not None:
                    schedule.barrier()
                    schedule.call(interleaved_waveform)
                    schedule.barrier()
            for gate in inverse:
                add_gate(gate)
        return schedule

    def _rb_experiment(
        self,
        targets: Collection[str] | str,
        *,
        n_cliffords_range: Any | None,
        n_trials: int | None,
        seeds: Any | None,
        max_n_cliffords: int | None,
        x90: Mapping[str, Any] | None,
        zx90: Mapping[str, Any] | None,
        interleaved_clifford: Any | None,
        interleaved_waveform: Mapping[str, Any] | None,
        plot: bool | None,
        include_decoherence: bool,
    ) -> Any:
        np, pd, qx, _qt, Result, _StateClassifierGMM, _Control, QuantumSimulator = (
            _simulation_dependencies()
        )
        from qubex.analysis import fitting

        target_labels = [targets] if isinstance(targets, str) else list(targets)
        if n_trials is None:
            n_trials = 8
        if n_cliffords_range is None:
            max_n = 16 if max_n_cliffords is None else int(max_n_cliffords)
            n_cliffords_range = [0]
            n = 1
            while n <= max_n:
                n_cliffords_range.append(n)
                n *= 2
        n_cliffords_range = np.asarray(n_cliffords_range, dtype=int)
        if seeds is None:
            seeds = np.arange(n_trials, dtype=int)
        else:
            seeds = np.asarray(seeds, dtype=int)
            n_trials = len(seeds)

        simulator = QuantumSimulator(self._qx_system(include_decoherence=include_decoherence))
        data: dict[str, Any] = {}
        figures: dict[str, Any] = {}
        for target in target_labels:
            rows = []
            trials = []
            for n_cliffords in n_cliffords_range:
                values = []
                for seed in seeds:
                    sequence = self.rb_sequence(
                        target,
                        n=int(n_cliffords),
                        x90=x90,
                        zx90=zx90.get(target) if zx90 else None,
                        interleaved_waveform=interleaved_waveform.get(target)
                        if interleaved_waveform
                        else None,
                        interleaved_clifford=interleaved_clifford,
                        seed=int(seed),
                    )
                    values.append(
                        self._rb_survival_probability(
                            target,
                            sequence,
                            simulator=simulator,
                        )
                    )
                values_array = np.asarray(values, dtype=float)
                trials.append(values_array)
                rows.append(
                    {
                        "n_cliffords": int(n_cliffords),
                        "mean": float(np.mean(values_array)),
                        "std": float(np.std(values_array)),
                    }
                )
            df = pd.DataFrame(rows)
            dimension = 4 if "-" in target else 2
            fit_result = fitting.fit_rb(
                target=target,
                x=n_cliffords_range,
                y=df["mean"].to_numpy(),
                error_y=df["std"].to_numpy() if n_trials > 1 else None,
                dimension=dimension,
                bounds=((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
                title="Interleaved randomized benchmarking"
                if interleaved_clifford
                else "Randomized benchmarking",
                xlabel="Number of Cliffords",
                ylabel="Survival probability",
                plot=False,
            )
            fit_payload = dict(fit_result) if getattr(fit_result, "data", None) else {}
            figure = fit_result.get_figure() if hasattr(fit_result, "get_figure") else None
            if plot:
                if figure is None:
                    figure = qx.viz.make_figure()
                    figure.add_scatter(
                        x=df["n_cliffords"],
                        y=df["mean"],
                        error_y={"type": "data", "array": df["std"]},
                        mode="lines+markers",
                        name=target,
                    )
                figure.update_layout(yaxis_range=[0, 1])
            if figure is not None:
                figures[target] = figure
            data[target] = {
                "n_cliffords": n_cliffords_range,
                "mean": df["mean"].to_numpy(),
                "std": df["std"].to_numpy(),
                "trials": np.vstack(trials),
                "seeds": np.asarray(seeds, dtype=int),
                "dataframe": df,
                "include_decoherence": include_decoherence,
                **fit_payload,
            }
        return Result(data=data, figures=figures, figure=next(iter(figures.values()), None))

    def _rb_survival_probability(
        self,
        target: str,
        sequence: Any,
        *,
        simulator: Any,
    ) -> float:
        np, _pd, _qx, _qt, _Result, _StateClassifierGMM, _Control, _QuantumSimulator = (
            _simulation_dependencies()
        )
        schedule = materialize_pulse_schedule_for_simulation(
            self._annotate_schedule_metadata(sequence)
        )
        pulse_ranges = schedule.get_pulse_ranges() if hasattr(schedule, "get_pulse_ranges") else {}
        has_active_pulse = any(
            pulse_range.start != pulse_range.stop
            for ranges in pulse_ranges.values()
            for pulse_range in ranges
        )
        if not has_active_pulse:
            return 1.0
        if "-" in target:
            control_qubit, target_qubit = target.split("-", 1)
            result = simulator.mesolve(
                schedule,
                initial_state={control_qubit: "0", target_qubit: "0"},
                n_samples=2,
            )
            probabilities = self._computational_probabilities(result)
            return float(probabilities["00"])
        result = simulator.mesolve(
            schedule,
            initial_state={target: "0"},
            n_samples=2,
        )
        populations = result._get_population(result.get_substates(target)[-1])
        return float(np.real(populations[0]))

    def _qubit_topology(self, index: int, label: str) -> dict[str, Any]:
        t1, t2 = self._qubit_lifetime(index)
        x, y = self.positions[index]
        qubit = {
            "id": index,
            "physical_id": _label_to_qid(label),
            "label": label,
            "position": {"x": x, "y": y},
            "frequency": self.qubit_frequencies[index],
            "anharmonicity": self.qubit_anharmonicities[index],
            "readout_frequency": self.readout_frequencies[index],
            "mux": self._qubit_muxes.get(label),
            "qubit_lifetime": {"t1": t1, "t2": t2},
            "gate_duration": {
                "rz": 0,
                "sx": self.hpi_duration,
                "sxdg": self.hpi_duration,
                "x": self.pi_duration,
                "y": self.pi_duration,
                "measure": self.readout_duration,
            },
        }
        if self.single_qubit_fidelity is not None:
            qubit["fidelity"] = self.single_qubit_fidelity
        readout_assignment_error = self.readout_assignment_errors.get(
            label,
            self.readout_assignment_error,
        )
        if readout_assignment_error is not None:
            qubit["meas_error"] = {
                "prob_meas1_prep0": readout_assignment_error / 2,
                "prob_meas0_prep1": readout_assignment_error / 2,
                "readout_assignment_error": readout_assignment_error,
            }
        return qubit

    def _coupling_topology(self) -> dict[str, Any]:
        gate_duration = {}
        if self.rzx90_duration is not None:
            gate_duration["rzx90"] = self.rzx90_duration
        if self.cx_duration is not None:
            gate_duration["cx"] = self.cx_duration
        coupling = {
            "control": 0,
            "target": 1,
            "coupling_strength_mhz": self.coupling_strength * 1000.0,
        }
        if self.two_qubit_fidelity is not None:
            coupling["fidelity"] = self.two_qubit_fidelity
        if gate_duration:
            coupling["gate_duration"] = gate_duration
        return coupling

    def _target_labels(self, targets: Collection[str | int] | str | int | None) -> list[str]:
        if targets is None:
            return list(self.qubit_labels)
        if isinstance(targets, int):
            return [_qid_to_label(targets, 10)]
        if isinstance(targets, str):
            return list(self._normalize_qubit_labels([targets]) or (targets,))
        return list(self._normalize_qubit_labels(targets) or ())

    @staticmethod
    def _normalize_qubit_labels(
        values: Collection[str | int] | None,
    ) -> tuple[str, ...] | None:
        if values is None:
            return None
        labels = []
        for value in values:
            if isinstance(value, int):
                labels.append(_qid_to_label(value, 10))
            else:
                text = str(value)
                labels.append(_qid_to_label(int(text), 10) if text.isdigit() else text)
        return tuple(labels)

    @staticmethod
    def _normalize_mux_labels(
        values: Collection[str | int] | None,
    ) -> tuple[str, ...]:
        if values is None:
            return ()
        labels = []
        for value in values:
            if isinstance(value, int):
                labels.append(f"M{value:02}")
                continue
            text = str(value)
            labels.append(f"M{int(text):02}" if text.isdigit() else text)
        return tuple(labels)

    @classmethod
    def _qubit_labels_from_muxes(
        cls,
        muxes: Collection[str | int] | None,
    ) -> tuple[str, ...] | None:
        mux_labels = cls._normalize_mux_labels(muxes)
        if not mux_labels:
            return None
        labels = []
        for mux_label in mux_labels:
            digits = "".join(character for character in mux_label if character.isdigit())
            if not digits:
                continue
            mux_index = int(digits)
            labels.extend([_qid_to_label(2 * mux_index, 10), _qid_to_label(2 * mux_index + 1, 10)])
        return tuple(dict.fromkeys(labels)) or None

    @classmethod
    def _infer_mux_labels(cls, qubits: Collection[str]) -> tuple[str, ...]:
        mux_indices = []
        for qubit in qubits:
            digits = "".join(character for character in str(qubit) if character.isdigit())
            if digits:
                mux_indices.append(int(digits) // 2)
        return tuple(f"M{index:02}" for index in dict.fromkeys(mux_indices))

    @classmethod
    def _assign_qubit_muxes(
        cls,
        qubits: Collection[str],
        muxes: Collection[str],
    ) -> dict[str, str]:
        inferred = cls._infer_mux_labels(qubits)
        mux_labels = tuple(muxes) or inferred
        return {
            qubit: (
                mux_labels[index // 2] if index // 2 < len(mux_labels) else inferred[index // 2]
            )
            for index, qubit in enumerate(qubits)
            if inferred
        }

    @staticmethod
    def _pad_float_tuple(
        values: Collection[float] | None,
        defaults: tuple[float, ...],
        size: int,
    ) -> tuple[float, ...]:
        source = tuple(float(value) for value in (values or defaults))
        if len(source) >= size:
            return source[:size]
        return source + tuple(source[-1] for _ in range(size - len(source)))

    def _result(
        self,
        *,
        data: Any | None = None,
        figure: Any | None = None,
        figures: Mapping[str, Any] | None = None,
    ) -> Any:
        try:
            from qubex.experiment.models.result import Result
        except ImportError:
            return _FallbackResult(data=data, figure=figure, figures=dict(figures or {}))
        return Result(data=data, figure=figure, figures=dict(figures or {}))

    def _sweep_stub(self, name: str, *args: Any, **kwargs: Any) -> Any:
        import numpy as np

        values = kwargs.get("values", np.linspace(0.0, 1.0, 11))
        return self._result(
            data={
                "name": name,
                "values": values,
                "response": np.zeros(len(values), dtype=float),
            }
        )

    def _lightweight_drag_calibration(
        self,
        targets: Collection[str] | str | None,
        *,
        angle: float,
    ) -> Any:
        import numpy as np

        data = {}
        for target in self._target_labels(targets):
            index = self.qubit_labels.index(target)
            duration = self.hpi_duration if angle < np.pi else self.pi_duration
            beta = -0.5 / (2.0 * np.pi * self.qubit_anharmonicities[index])
            pulse = self._default_drag_pulse(target, angle=angle)
            if angle < np.pi:
                self.drag_hpi_pulses[target] = pulse
            else:
                self.drag_pi_pulses[target] = pulse
            data[target] = {
                "target": target,
                "duration": duration,
                "amplitude": float(angle / np.pi),
                "beta": float(beta),
            }
        return self._result(data=data)

    def _lightweight_pulse_tomography(
        self,
        sequence: Any,
        *,
        initial_state: Mapping[str, str] | None = None,
    ) -> Any:
        import numpy as np

        labels = self._tomography_targets(sequence)
        initial = dict(initial_state or {})
        times = np.linspace(0.0, 1.0, 51)
        data = {}
        for label in labels:
            sign = -1.0 if initial.get(label, "0") == "1" else 1.0
            data[label] = np.column_stack(
                [
                    np.zeros_like(times),
                    np.sin(np.pi * times),
                    sign * np.cos(np.pi * times),
                ]
            )
        return self._result(data=data)

    def _lightweight_rb_result(
        self,
        targets: Collection[str] | str,
        *,
        n_cliffords_range: Any | None,
        max_n_cliffords: int | None,
        interleaved_clifford: Any | None = None,
    ) -> Any:
        import numpy as np

        target_label = targets if isinstance(targets, str) else "-".join(targets)
        if n_cliffords_range is None:
            stop = max_n_cliffords or 1000
            n_cliffords = np.arange(0, stop + 1, max(stop // 10, 1))
        else:
            n_cliffords = np.asarray(list(n_cliffords_range), dtype=float)
        decay = np.exp(-n_cliffords / max(float(n_cliffords[-1] or 1.0), 1.0) * 0.1)
        data = {
            target_label: SimpleNamespace(
                target=target_label,
                n_cliffords=n_cliffords,
                survival_probability=decay,
                interleaved_clifford=interleaved_clifford,
                fidelity=float(decay[-1]),
                plot=lambda *args, **kwargs: None,
            )
        }
        return _FallbackExperimentResult(data=data, status="success")

    def _lightweight_state_distribution(
        self,
        targets: Collection[str] | str | None,
        *,
        n_states: int,
        n_shots: int,
    ) -> Any:
        import numpy as np

        rng = np.random.default_rng(7)
        centers = [complex(index, 0.25 * index) for index in range(n_states)]
        distributions = []
        for state in range(n_states):
            shot_map = {}
            for target in self._target_labels(targets):
                noise = 0.05 * (rng.normal(size=n_shots) + 1j * rng.normal(size=n_shots))
                shot_map[target] = np.full(n_shots, centers[state], dtype=complex) + noise
            distributions.append(shot_map)
        return self._result(data={"distributions": distributions})

    def _lightweight_cr_params(self, control_qubit: str, target_qubit: str) -> Any:
        control_index = self.qubit_labels.index(control_qubit)
        target_index = self.qubit_labels.index(target_qubit)
        frequency_diff = (
            self.qubit_frequencies[control_index] - self.qubit_frequencies[target_index]
        )
        duration = 160.0
        param = {
            "control": control_qubit,
            "target": target_qubit,
            "duration": duration,
            "ramptime": 16.0,
            "cr_amplitude": 0.25 * abs(frequency_diff or 1.0),
            "cr_phase": 0.0,
            "cancel_amplitude": 0.01,
            "cancel_phase": 0.0,
            "cr_amplitude_max": 0.75 * abs(frequency_diff or 1.0),
        }
        label = f"{control_qubit}-{target_qubit}"
        self.cr_params[label] = param
        self.rzx90_duration = 2.0 * duration + 2.0 * self.pi_duration
        self.cx_duration = self.rzx90_duration + self.hpi_duration
        return self._result(data={"cr_param": param})

    def _lightweight_zx90(self, control_qubit: str, target_qubit: str) -> Any:
        import qubex as qx

        label = f"{control_qubit}-{target_qubit}"
        if label not in self.cr_params:
            self._lightweight_cr_params(control_qubit, target_qubit)
        param = self.cr_params[label]
        with qx.PulseSchedule([control_qubit, label, target_qubit]) as schedule:
            schedule.add(
                label,
                qx.pulse.FlatTop(
                    duration=param["duration"],
                    amplitude=param["cr_amplitude"],
                    tau=param["ramptime"],
                    phase=param["cr_phase"],
                ),
            )
            schedule.add(
                target_qubit,
                qx.pulse.FlatTop(
                    duration=param["duration"],
                    amplitude=param["cancel_amplitude"],
                    tau=param["ramptime"],
                    phase=param["cancel_phase"],
                ),
            )
        return schedule

    def _lightweight_bell_state(
        self,
        *,
        control_basis: str | None,
        target_basis: str | None,
    ) -> Any:
        import numpy as np

        raw = np.array([0.5, 0.0, 0.0, 0.5], dtype=float)
        return self._result(
            data={
                "raw": raw,
                "mitigated": raw.copy(),
                "probabilities": {
                    "00": 0.5,
                    "01": 0.0,
                    "10": 0.0,
                    "11": 0.5,
                },
                "basis": f"{control_basis or 'Z'}{target_basis or 'Z'}",
            }
        )

    def _synthetic_rabi_param(self, target: str, *, frequency: float | None = None) -> Any:
        try:
            from qubex.experiment.models.rabi_param import RabiParam
        except ImportError:
            RabiParam = None

        values = {
            "target": target,
            "amplitude": 0.5,
            "frequency": frequency if frequency is not None else 1.0 / (2.0 * self.pi_duration),
            "phase": 0.0,
            "offset": 0.0,
            "noise": 0.0,
            "angle": 0.0,
            "distance": 0.5,
            "r2": 1.0,
            "reference_phase": 0.0,
        }
        if RabiParam is None:
            return SimpleNamespace(**values)
        return RabiParam(**values)

    def _experiment_result(self, data: Mapping[str, Any], **kwargs: Any) -> Any:
        try:
            from qubex.experiment.models.experiment_result import ExperimentResult
        except ImportError:
            return _FallbackExperimentResult(data=data, **kwargs)
        return ExperimentResult(data=dict(data), **kwargs)

    def _coherence_result(
        self,
        targets: Collection[str] | str | None,
        *,
        time_range: Any | None,
        experiment: str,
        plot: bool,
        xaxis_type: str,
        detuning: float = 0.001,
        second_rotation_axis: str = "Y",
        spectator_state: str = "0",
        n_cpmg: int | None = None,
        shots: int | None = None,
        interval: float | None = None,
        use_simulator: bool = False,
    ) -> Any:
        import numpy as np

        if time_range is None:
            if experiment == "ramsey":
                time_values = np.arange(0.0, 10001.0, 100.0)
            elif experiment == "t1":
                time_values = np.geomspace(100.0, 200_000.0, 51)
            else:
                time_values = np.geomspace(300.0, 200_000.0, 51)
        else:
            time_values = np.asarray(time_range, dtype=float)

        labels = self._target_labels(targets)
        shots = 1024 if shots is None else int(shots)
        interval = 0.0 if interval is None else float(interval)
        target_groups = [labels]
        if experiment in {"t1", "t2"}:
            subgroups = target_groups
            print(f"Target qubits: {labels}")
            print(f"Subgroups: {subgroups}")
            experiment_name = "T1" if experiment == "t1" else "T2"
            for idx, subgroup in enumerate(subgroups):
                if subgroup:
                    print(
                        f"({idx + 1}/{len(subgroups)}) Conducting {experiment_name} "
                        f"experiment for {subgroup}...\n"
                    )
        else:
            subgroups = target_groups

        def make_value(
            *,
            target: str,
            data: Any,
            sweep_range: Any,
            title: str,
            xlabel: str,
            ylabel: str,
            xaxis: str,
            yaxis: str = "linear",
            **fields: Any,
        ) -> Any:
            value = SimpleNamespace(
                target=target,
                data=data,
                sweep_range=sweep_range,
                title=title,
                xlabel=xlabel,
                ylabel=ylabel,
                xaxis_type=xaxis,
                yaxis_type=yaxis,
                **fields,
            )

            def _plot(*_: Any, return_figure: bool = False, **plot_kwargs: Any) -> Any:
                if title in {"T1 decay", "T2 echo", "Ramsey"}:
                    values = np.asarray(data, dtype=complex)
                    x_values = np.asarray(sweep_range, dtype=float)
                    normalized = 2.0 * values.imag
                    if title == "T1 decay":
                        tau = float(fields.get("t1", np.nan))
                        y_values = 0.5 * (1.0 - normalized)
                        fit_values = np.exp(-x_values / max(tau, 1.0))
                        fit_title = "T1"
                        ylabel_fit = "Population"
                        annotation = (
                            f"τ = {tau * 1e-3:.1f} μs, R² = {float(fields.get('r2', np.nan)):.3f}"
                        )
                    elif title == "T2 echo":
                        tau = float(fields.get("t2", np.nan))
                        y_values = 0.5 * (1.0 + normalized)
                        fit_values = np.exp(-x_values / max(tau, 1.0))
                        fit_title = "T2 echo"
                        ylabel_fit = "Population"
                        annotation = (
                            f"τ = {tau * 1e-3:.1f} μs, R² = {float(fields.get('r2', np.nan)):.3f}"
                        )
                    else:
                        tau = float(fields.get("t2", np.nan))
                        ramsey_freq = float(fields.get("ramsey_freq", 0.0))
                        y_values = normalized
                        fit_values = np.exp(-x_values / max(tau, 1.0)) * np.cos(
                            2.0 * np.pi * ramsey_freq * x_values
                        )
                        fit_title = "Ramsey fringe"
                        ylabel_fit = "Signal (arb. units)"
                        annotation = f"R² = {float(fields.get('r2', np.nan)):.3f}"
                    return _plot_fit_series(
                        target=target,
                        x=x_values,
                        y=y_values,
                        fit_y=fit_values,
                        title=fit_title,
                        xlabel="Time (μs)",
                        ylabel=ylabel_fit,
                        filename=fit_title.lower().replace(" ", "_"),
                        annotation=annotation,
                        xaxis_type=xaxis,
                        yaxis_type=yaxis,
                        return_figure=return_figure,
                        **plot_kwargs,
                    )
                return _plot_iq_series(
                    target=target,
                    x=sweep_range,
                    data=data,
                    title=f"{title} : {target}",
                    xlabel=xlabel,
                    ylabel=ylabel,
                    filename=title.lower().replace(" ", "_"),
                    xaxis_type=xaxis,
                    yaxis_type=yaxis,
                    return_figure=return_figure,
                    **plot_kwargs,
                )

            def _fit(*_: Any, **__: Any) -> dict[str, Any]:
                fit_result = {
                    "fig": _plot(return_figure=True),
                    "r2": float(fields.get("r2", 1.0)),
                }
                if title == "Ramsey":
                    fit_result.update(
                        {
                            "f": float(fields.get("ramsey_freq", 0.0)),
                            "f_err": float(fields.get("ramsey_freq_err", 0.0)),
                            "tau_err": float(fields.get("t2_err", 0.0)),
                        }
                    )
                return fit_result

            value.plot = _plot
            value.fit = _fit
            return value

        if not use_simulator:
            if experiment == "ramsey":
                spectator_qubits = [label for label in self.qubit_labels if label not in labels]
                print(f"Target qubits: {labels}")
                print(f"Spectator qubits: {spectator_qubits}")

            data: dict[str, Any] = {}
            for target in labels:
                ge_target = self._ge_label(target)
                index = self.qubit_labels.index(ge_target)
                t1_us, t2_us = self._qubit_lifetime(index)
                t1_ns = float(t1_us) * 1000.0
                t2_ns = float(t2_us) * 1000.0
                target_time_values = (
                    self._coherence_time_values(time_values, index)
                    if experiment in {"t1", "t2"}
                    else time_values
                )
                rabi_param = self._rabi_params.get(target) or self._synthetic_rabi_param(target)

                if experiment == "t1":
                    population = np.exp(-target_time_values / max(t1_ns, 1.0))
                    signal = 0.5 + 0.5j * (1.0 - 2.0 * population)
                    data[target] = make_value(
                        target=target,
                        data=signal,
                        sweep_range=target_time_values,
                        title="T1 decay",
                        xlabel="Time (us)",
                        ylabel="Measured value",
                        xaxis=xaxis_type,
                        rabi_param=rabi_param,
                        state_centers=self.state_centers.get(ge_target),
                        t1=t1_ns,
                        t1_err=0.0,
                        r2=1.0,
                    )
                elif experiment == "t2":
                    envelope = np.exp(-target_time_values / max(t2_ns, 1.0))
                    signal = 0.5 + 0.5j * (2.0 * envelope - 1.0)
                    data[target] = make_value(
                        target=target,
                        data=signal,
                        sweep_range=target_time_values,
                        title="T2 echo",
                        xlabel="Time (us)",
                        ylabel="Measured value",
                        xaxis=xaxis_type,
                        rabi_param=rabi_param,
                        state_centers=self.state_centers.get(ge_target),
                        t2=t2_ns,
                        t2_err=0.0,
                        r2=1.0,
                    )
                else:
                    envelope = np.exp(-time_values / max(t2_ns, 1.0))
                    ramsey_freq = abs(detuning)
                    signal = 0.5 + 0.5j * envelope * np.cos(2.0 * np.pi * ramsey_freq * time_values)
                    bare_freq = self.qubit_frequencies[index]
                    data[target] = make_value(
                        target=target,
                        data=signal,
                        sweep_range=time_values,
                        title="Ramsey",
                        xlabel="Time (ns)",
                        ylabel="Measured value",
                        xaxis=xaxis_type,
                        rabi_param=rabi_param,
                        state_centers=self.state_centers.get(ge_target),
                        t2=t2_ns,
                        ramsey_freq=ramsey_freq,
                        bare_freq=bare_freq,
                        r2=1.0,
                    )
                    print(f"Bare frequency with |{spectator_state}>:")
                    print(f"  {target}: {bare_freq:.6f}")
                    print("")

            result = self._experiment_result(data)
            if plot:
                result.plot()
            return result

        from qxpulse import PulseSchedule, Waveform
        from qxpulse.blank import Blank
        from qxpulse.library.cpmg import CPMG

        time_values = self.discretize_time_range(
            time_values,
            sampling_period=float(Waveform.SAMPLING_PERIOD),
        )

        data: dict[str, Any] = {}
        for subgroup in subgroups:
            if not subgroup:
                continue

            if experiment == "t1":

                def sequence(T: float, subgroup: list[str] = subgroup) -> Any:
                    with PulseSchedule(subgroup) as ps:
                        for target in subgroup:
                            ps.set_frequency(
                                target,
                                self.qubit_frequencies[
                                    self.qubit_labels.index(self._ge_label(target))
                                ],
                            )
                            ps.add(target, self.get_hpi_pulse(target).repeated(2))
                            ps.add(target, Blank(T))
                    return ps

                sweep_result = self.sweep_parameter(
                    sequence=sequence,
                    sweep_range=time_values,
                    targets=subgroup,
                    shots=shots,
                    interval=interval,
                    plot=False,
                    title="T1 decay",
                    xlabel="Time (us)",
                    ylabel="Measured value",
                    xaxis_type=xaxis_type,
                    use_simulator=True,
                )
                for target, sweep_data in sweep_result.data.items():
                    ge_target = self._ge_label(target)
                    index = self.qubit_labels.index(ge_target)
                    t1_us, _ = self._qubit_lifetime(index)
                    t1_ns = float(t1_us) * 1000.0
                    sweep_range = self._coherence_time_values(
                        np.asarray(sweep_data.sweep_range, dtype=float),
                        index,
                    )
                    rabi_param = self._rabi_params.get(target) or self._synthetic_rabi_param(target)
                    data[target] = make_value(
                        target=target,
                        data=np.asarray(sweep_data.data, dtype=complex),
                        sweep_range=sweep_range,
                        title="T1 decay",
                        xlabel="Time (us)",
                        ylabel="Measured value",
                        xaxis=xaxis_type,
                        rabi_param=rabi_param,
                        state_centers=self.state_centers.get(ge_target),
                        t1=t1_ns,
                        t1_err=0.0,
                        r2=1.0,
                    )

            elif experiment == "t2":
                cpmg_count = 1 if n_cpmg is None else int(n_cpmg)

                def sequence(T: float, subgroup: list[str] = subgroup) -> Any:
                    with PulseSchedule(subgroup) as ps:
                        for target in subgroup:
                            ge_target = self._ge_label(target)
                            index = self.qubit_labels.index(ge_target)
                            ps.set_frequency(target, self.qubit_frequencies[index])
                            hpi = self.get_hpi_pulse(target)
                            pi = hpi.repeated(2).shifted(np.pi / 2)
                            ps.add(target, hpi)
                            if n_cpmg is not None:
                                total_blank = T - pi.duration * cpmg_count
                                if total_blank > 0:
                                    total_blank_samples = int(
                                        np.floor(
                                            total_blank / float(Waveform.SAMPLING_PERIOD) + 1e-9
                                        )
                                    )
                                    tau_samples = total_blank_samples // (2 * cpmg_count)
                                    tau = tau_samples * float(Waveform.SAMPLING_PERIOD)
                                    ps.add(target, CPMG(tau=tau, pi=pi, n=cpmg_count))
                                else:
                                    ps.add(target, Blank(T))
                            else:
                                tau = pi.duration * 5
                                cpmg = CPMG(tau=tau, pi=pi, n=2)
                                n_repeats = int(T // cpmg.duration)
                                remainder = T % cpmg.duration
                                if n_repeats > 0:
                                    ps.add(target, cpmg.repeated(n_repeats))
                                if remainder > 0:
                                    ps.add(target, Blank(remainder))
                            ps.add(target, hpi.scaled(-1))
                    return ps

                sweep_result = self.sweep_parameter(
                    sequence=sequence,
                    sweep_range=time_values,
                    targets=subgroup,
                    shots=shots,
                    interval=interval,
                    plot=False,
                    xaxis_type=xaxis_type,
                    use_simulator=True,
                )
                for target, sweep_data in sweep_result.data.items():
                    ge_target = self._ge_label(target)
                    index = self.qubit_labels.index(ge_target)
                    _, t2_us = self._qubit_lifetime(index)
                    t2_ns = float(t2_us) * 1000.0
                    sweep_range = self._coherence_time_values(
                        np.asarray(sweep_data.sweep_range, dtype=float),
                        index,
                    )
                    rabi_param = self._rabi_params.get(target) or self._synthetic_rabi_param(target)
                    data[target] = make_value(
                        target=target,
                        data=np.asarray(sweep_data.data, dtype=complex),
                        sweep_range=sweep_range,
                        title="T2 echo",
                        xlabel="Time (us)",
                        ylabel="Measured value",
                        xaxis=xaxis_type,
                        rabi_param=rabi_param,
                        state_centers=self.state_centers.get(ge_target),
                        t2=t2_ns,
                        t2_err=0.0,
                        r2=1.0,
                    )

            else:
                spectator_qubits = [label for label in self.qubit_labels if label not in subgroup]
                print(f"Target qubits: {subgroup}")
                print(f"Spectator qubits: {spectator_qubits}")

                def sequence(T: float, subgroup: list[str] = subgroup) -> Any:
                    target_list_local = list(subgroup)
                    if spectator_state != "0":
                        target_list_local = list(dict.fromkeys([*subgroup, *spectator_qubits]))
                    with PulseSchedule(target_list_local) as ps:
                        for target in subgroup:
                            ge_target = self._ge_label(target)
                            index = self.qubit_labels.index(ge_target)
                            ps.set_frequency(target, self.qubit_frequencies[index] + detuning)
                        for spectator in spectator_qubits:
                            if spectator in target_list_local:
                                index = self.qubit_labels.index(spectator)
                                ps.set_frequency(spectator, self.qubit_frequencies[index])
                        if spectator_state != "0":
                            for spectator in spectator_qubits:
                                if spectator in target_list_local:
                                    ps.add(
                                        spectator,
                                        self.get_pulse_for_state(spectator, spectator_state),
                                    )
                            ps.barrier()
                        for target in subgroup:
                            x90 = self.get_hpi_pulse(target)
                            ps.add(target, x90)
                            ps.add(target, Blank(T))
                            if second_rotation_axis == "X":
                                ps.add(target, x90.shifted(np.pi))
                            else:
                                ps.add(target, x90.shifted(-0.5 * np.pi))
                    return ps

                sweep_result = self.sweep_parameter(
                    sequence=sequence,
                    sweep_range=time_values,
                    targets=subgroup,
                    shots=shots,
                    interval=interval,
                    plot=False,
                    use_simulator=True,
                )
                for target, sweep_data in sweep_result.data.items():
                    ge_target = self._ge_label(target)
                    _, t2_us = self._qubit_lifetime(self.qubit_labels.index(ge_target))
                    t2_ns = float(t2_us) * 1000.0
                    bare_freq = self.qubit_frequencies[self.qubit_labels.index(ge_target)]
                    rabi_param = self._rabi_params.get(target) or self._synthetic_rabi_param(target)
                    data[target] = make_value(
                        target=target,
                        data=np.asarray(sweep_data.data, dtype=complex),
                        sweep_range=np.asarray(sweep_data.sweep_range, dtype=float),
                        title="Ramsey",
                        xlabel="Time (ns)",
                        ylabel="Measured value",
                        xaxis=xaxis_type,
                        rabi_param=rabi_param,
                        state_centers=self.state_centers.get(ge_target),
                        t2=t2_ns,
                        ramsey_freq=abs(detuning),
                        bare_freq=bare_freq,
                        r2=1.0,
                    )
                    print(f"Bare frequency with |{spectator_state}>:")
                    print(f"  {target}: {bare_freq:.6f}")
                    print("")

        result = self._experiment_result(data)
        if plot:
            result.plot()
        return result

    def _chevron_pattern_result(
        self,
        targets: Collection[str] | str | None = None,
        *,
        detuning_range: Any | None = None,
        time_range: Any | None = None,
        frequencies: dict[str, float] | None = None,
        amplitudes: dict[str, float] | None = None,
        plot: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        import numpy as np

        if plot is None:
            plot = True
        use_simulator = bool(kwargs.get("use_simulator", False))
        labels = self._target_labels(targets)
        detunings = (
            np.linspace(-0.05, 0.05, 51)
            if detuning_range is None
            else np.asarray(detuning_range, dtype=float)
        )
        times = (
            np.linspace(0.0, 2.0 * self.pi_duration, 41)
            if time_range is None
            else np.asarray(time_range, dtype=float)
        )
        times = self.discretize_time_range(times, sampling_period=float(self.dt * 1e9))
        frequencies = frequencies or {
            target: self.qubit_frequencies[self.qubit_labels.index(self._ge_label(target))]
            for target in labels
        }
        amplitudes = amplitudes or {target: 1.0 for target in labels}

        chevron_data = {}
        rabi_rates = {}
        rabi_fit_r2 = {}
        resonant_frequencies = {}
        figures = {}

        if not use_simulator:
            for target in labels:
                ge_target = self._ge_label(target)
                base_rate = self.calc_rabi_rate(target, amplitude=amplitudes.get(target, 1.0))
                rates = np.sqrt(base_rate**2 + detunings**2)
                phase = 2.0 * np.pi * np.outer(times, rates)
                lifetime_ns = self._qubit_lifetime(self.qubit_labels.index(ge_target))[1] * 1000.0
                envelope = np.exp(-times[:, None] / max(lifetime_ns, 1.0))
                response = 0.5 * (1.0 - np.cos(phase) * envelope)

                chevron_data[target] = response
                rabi_rates[target] = rates
                rabi_fit_r2[target] = np.ones_like(rates)
                resonant_frequencies[target] = float(frequencies[target])

                figure = self._chevron_figure(
                    target=target,
                    control_frequencies=frequencies[target] + detunings,
                    time_range=times,
                    data=response,
                    amplitude=amplitudes.get(target, 1.0),
                )
                if figure is not None:
                    figures[target] = figure
                    if plot:
                        _show_figure(
                            figure,
                            filename=f"chevron_pattern_{target}",
                            width=600,
                            height=400,
                        )

            return self._result(
                data={
                    "time_range": times,
                    "detuning_range": detunings,
                    "frequencies": frequencies,
                    "chevron_data": chevron_data,
                    "rabi_rates": rabi_rates,
                    "rabi_fit_r2": rabi_fit_r2,
                    "resonant_frequencies": resonant_frequencies,
                    "fig": figures,
                },
                figures=figures,
            )

        from qxpulse import PulseSchedule, Rect

        print(f"Targets : {labels}")
        subgroups = [labels]
        for idx, subgroup in enumerate(subgroups):
            if not subgroup:
                continue

            print(f"Subgroup ({idx + 1}/{len(subgroups)}) : {subgroup}")
            chevron_data_buffer: dict[str, list[np.ndarray]] = {target: [] for target in subgroup}
            rabi_rates_buffer: dict[str, list[float]] = {target: [] for target in subgroup}
            rabi_fit_r2_buffer: dict[str, list[float]] = {target: [] for target in subgroup}

            for detuning in detunings:

                def sequence(T: float, subgroup: list[str] = subgroup) -> Any:
                    with PulseSchedule(subgroup) as ps:
                        for target in subgroup:
                            ps.set_frequency(target, frequencies[target] + float(detuning))
                            ps.add(
                                target,
                                Rect(
                                    duration=float(T),
                                    amplitude=float(amplitudes.get(target, 1.0)),
                                ),
                            )
                    return ps

                sweep_result = self.sweep_parameter(
                    sequence=sequence,
                    sweep_range=times,
                    targets=subgroup,
                    shots=1024,
                    interval=0.0,
                    plot=False,
                    use_simulator=True,
                    frequencies={
                        target: frequencies[target] + float(detuning) for target in subgroup
                    },
                )
                for target, sweep_data in sweep_result.data.items():
                    values = np.asarray(sweep_data.normalized, dtype=float)
                    chevron_data_buffer[target].append(values)
                    if len(times) > 1:
                        centered = values - float(np.mean(values))
                        if np.allclose(centered, 0.0):
                            rate = 0.0
                            r2 = 0.0
                        else:
                            dt = float(np.median(np.diff(times)))
                            spectrum = np.fft.rfft(centered)
                            freqs = np.fft.rfftfreq(len(centered), d=dt)
                            if len(freqs) > 1:
                                best = 1 + int(np.argmax(np.abs(spectrum[1:])))
                                rate = float(freqs[best])
                                total_power = float(np.sum(np.abs(spectrum[1:]) ** 2))
                                peak_power = float(np.abs(spectrum[best]) ** 2)
                                r2 = peak_power / total_power if total_power > 0 else 0.0
                            else:
                                rate = 0.0
                                r2 = 0.0
                    else:
                        rate = 0.0
                        r2 = 0.0
                    rabi_rates_buffer[target].append(rate)
                    rabi_fit_r2_buffer[target].append(r2)

            for target in subgroup:
                response = np.asarray(chevron_data_buffer[target], dtype=float).T
                chevron_data[target] = response
                rabi_rates[target] = np.asarray(rabi_rates_buffer[target], dtype=float)
                rabi_fit_r2[target] = np.asarray(rabi_fit_r2_buffer[target], dtype=float)
                resonant_frequencies[target] = float(
                    frequencies[target] + detunings[int(np.argmax(np.mean(response, axis=0)))]
                )

                figure = self._chevron_figure(
                    target=target,
                    control_frequencies=frequencies[target] + detunings,
                    time_range=times,
                    data=response,
                    amplitude=amplitudes.get(target, 1.0),
                )
                if figure is not None:
                    figures[target] = figure
                    if plot:
                        _show_figure(
                            figure,
                            filename=f"chevron_pattern_{target}",
                            width=600,
                            height=400,
                        )

        return self._result(
            data={
                "time_range": times,
                "detuning_range": detunings,
                "frequencies": frequencies,
                "chevron_data": chevron_data,
                "rabi_rates": rabi_rates,
                "rabi_fit_r2": rabi_fit_r2,
                "resonant_frequencies": resonant_frequencies,
                "fig": figures,
            },
            figures=figures,
        )

    def _chevron_figure(
        self,
        *,
        target: str,
        control_frequencies: Any,
        time_range: Any,
        data: Any,
        amplitude: float,
    ) -> Any:
        try:
            import plotly.graph_objects as go
        except Exception:
            return None

        figure = _make_figure(width=600, height=400)
        if figure is None:
            return None
        figure.add_trace(
            go.Heatmap(
                x=control_frequencies,
                y=time_range,
                z=data,
                colorscale="Viridis",
            )
        )
        figure.update_layout(
            title=f"Chevron pattern : {target}",
            xaxis_title="Drive frequency (GHz)",
            yaxis_title="Time (ns)",
            width=600,
            height=400,
            margin={"t": 80},
            annotations=[
                {
                    "text": f"control_amplitude={amplitude:.6g}",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.0,
                    "y": 1.08,
                    "showarrow": False,
                    "font": {"size": 13, "family": "monospace"},
                }
            ],
        )
        return figure

    def _rabi_result(
        self,
        *,
        amplitudes: Mapping[str, float],
        time_range: Any | None,
        ramptime: float | None,
        store_params: bool,
        transition: str,
    ) -> Any:
        import numpy as np

        try:
            from qubex.experiment.models.experiment_result import (
                ExperimentResult,
                RabiData,
            )
            from qubex.experiment.models.rabi_param import RabiParam
        except ImportError:
            ExperimentResult = None
            RabiData = None
            RabiParam = None

        if time_range is None:
            time_range_array = np.linspace(0.0, 2.0 * self.pi_duration, 41)
        else:
            time_range_array = np.asarray(time_range, dtype=float)
        effective_time_range = time_range_array + float(ramptime or 0.0)

        rabi_data = {}
        rabi_params = {}
        for input_label, amplitude in amplitudes.items():
            target = self._resolve_rabi_label(input_label, transition=transition)
            frequency = self.calc_rabi_rate(target, amplitude=float(amplitude))
            phase = 0.0
            oscillation = np.cos(2.0 * np.pi * frequency * effective_time_range + phase)
            data = 0.5 + 0.5j * oscillation

            if RabiParam is None:
                rabi_param = SimpleNamespace(
                    target=target,
                    amplitude=0.5,
                    frequency=frequency,
                    phase=phase,
                    offset=0.0,
                    noise=0.0,
                    angle=0.0,
                    distance=0.5,
                    r2=1.0,
                    reference_phase=0.0,
                )
            else:
                rabi_param = RabiParam(
                    target=target,
                    amplitude=0.5,
                    frequency=frequency,
                    phase=phase,
                    offset=0.0,
                    noise=0.0,
                    angle=0.0,
                    distance=0.5,
                    r2=1.0,
                    reference_phase=0.0,
                )
            rabi_params[target] = rabi_param

            if RabiData is None:
                value = SimpleNamespace(
                    target=target,
                    data=data,
                    time_range=effective_time_range,
                    rabi_param=rabi_param,
                    state_centers=self.state_centers.get(self._ge_label(target)),
                )
                value.normalized = 2.0 * np.asarray(data, dtype=complex).imag

                def _plot(
                    *,
                    target: str = target,
                    time_range: Any = effective_time_range,
                    normalized: Any = value.normalized,
                    normalize: bool = True,
                    return_figure: bool = False,
                    **plot_kwargs: Any,
                ) -> Any:
                    if normalize:
                        return _plot_normalized_series(
                            target=target,
                            x=time_range,
                            y=normalized,
                            title=f"Rabi oscillation : {target}",
                            xlabel="Drive duration (ns)",
                            ylabel="Normalized signal",
                            filename="rabi_data",
                            return_figure=return_figure,
                            **plot_kwargs,
                        )
                    return _plot_iq_series(
                        target=target,
                        x=time_range,
                        data=data,
                        title=f"Rabi oscillation : {target}",
                        xlabel="Drive duration (ns)",
                        ylabel="Signal (arb. units)",
                        filename="rabi_data",
                        return_figure=return_figure,
                        **plot_kwargs,
                    )

                value.plot = _plot
                rabi_data[target] = value
            else:
                rabi_data[target] = _NormalizedRabiData(
                    RabiData(
                        target=target,
                        data=data,
                        time_range=effective_time_range,
                        rabi_param=rabi_param,
                        state_centers=self.state_centers.get(self._ge_label(target)),
                    )
                )

        if store_params:
            self.store_rabi_params(rabi_params)

        if ExperimentResult is None:
            return _FallbackExperimentResult(data=rabi_data, rabi_params=rabi_params)
        return ExperimentResult(data=rabi_data, rabi_params=rabi_params)

    def _resolve_rabi_label(self, label: str, transition: str | None = None) -> str:
        text = str(label)
        if transition == "ef" and not self._is_ef_label(text):
            return f"{text}/ef"
        if transition == "ge" and self._is_ef_label(text):
            return self._ge_label(text)
        return text

    @staticmethod
    def _is_ef_label(label: str) -> bool:
        return label.endswith("/ef") or label.endswith(".ef") or label.startswith("EF")

    @staticmethod
    def _ge_label(label: str) -> str:
        if label.endswith("/ef"):
            return label[:-3]
        if label.endswith(".ef"):
            return label[:-3]
        if label.startswith("EF"):
            return "Q" + label[2:]
        return label

    def _qubit_lifetime(self, index: int) -> tuple[float, float]:
        if self.qubit_lifetimes is not None:
            return self.qubit_lifetimes[index]
        t1_base, t2_base = self.qubit_lifetime
        qid_jitter = ((index % 5) - 2) * 0.03
        t1 = float(t1_base) * (1.0 + qid_jitter + random.uniform(-0.04, 0.04))
        t2 = float(t2_base) * (0.88 - qid_jitter * 0.5 + random.uniform(-0.04, 0.04))
        return (t1, t2)

    def _coherence_time_values(self, time_values: Any, index: int) -> Any:
        import numpy as np

        qid_jitter = ((index % 7) - 3) * 0.01
        scale = 1.0 + qid_jitter + random.uniform(-0.025, 0.025)
        return np.asarray(time_values, dtype=float) * max(scale, 0.1)

    def _qx_system(self, *, include_decoherence: bool = True) -> Any:
        return build_qxsimulator_system(
            self.model(),
            qubit_dimension=3,
            include_decoherence=include_decoherence,
        )

    def _area_normalized_drag(self, duration: float, area: float, beta: float) -> Any:
        np, _pd, qx, _qt, _Result, _StateClassifierGMM, _Control, _QuantumSimulator = (
            _simulation_dependencies()
        )
        pulse = qx.pulse.Drag(duration=duration, amplitude=1.0, beta=beta, type="Gaussian")
        norm_factor = area / float(np.sum(np.abs(pulse.values) * pulse.SAMPLING_PERIOD))
        return pulse.scaled(norm_factor)

    def _tomography_targets(self, sequence: Any) -> list[str]:
        labels = getattr(sequence, "labels", self.qubit_labels)
        targets = []
        for label in labels:
            target = label.split("-", 1)[-1] if "-" in label else label
            if target in self.qubit_labels and target not in targets:
                targets.append(target)
        return targets or list(self.qubit_labels)

    def _bell_measurement_schedule(
        self,
        control_qubit: str,
        target_qubit: str,
        *,
        control_basis: str,
        target_basis: str,
        zx90: Any | None = None,
    ) -> Any:
        _np, _pd, qx, _qt, _Result, _StateClassifierGMM, _Control, _QuantumSimulator = (
            _simulation_dependencies()
        )
        cnot = self.cnot(control_qubit, target_qubit, zx90=zx90)
        with qx.PulseSchedule(list(cnot.labels)) as schedule:
            schedule.add(control_qubit, self.y90(control_qubit))
            schedule.call(cnot)
            if control_basis == "X":
                schedule.add(control_qubit, self.y90m(control_qubit))
            elif control_basis == "Y":
                schedule.add(control_qubit, self.x90(control_qubit))
            elif control_basis != "Z":
                raise ValueError(f"Unsupported control_basis: {control_basis!r}")
            if target_basis == "X":
                schedule.add(target_qubit, self.y90m(target_qubit))
            elif target_basis == "Y":
                schedule.add(target_qubit, self.x90(target_qubit))
            elif target_basis != "Z":
                raise ValueError(f"Unsupported target_basis: {target_basis!r}")
        return schedule

    def _annotate_schedule_metadata(self, schedule: Any) -> Any:
        if not hasattr(schedule, "labels"):
            return schedule
        channels = getattr(schedule, "_channels", {})
        for label in getattr(schedule, "labels", ()):
            target = None
            frequency = None
            if label in self.qubit_labels:
                index = self.qubit_labels.index(label)
                target = label
                frequency = self.qubit_frequencies[index]
            elif "-" in str(label):
                control, target_label = str(label).split("-", 1)
                if target_label in self.qubit_labels:
                    target = control
                    frequency = self.qubit_frequencies[self.qubit_labels.index(target_label)]
            if frequency is not None and hasattr(schedule, "set_frequency"):
                schedule.set_frequency(label, frequency)
            channel = channels.get(label) if isinstance(channels, dict) else None
            if channel is not None and target is not None:
                channel.target = target
        return schedule

    @staticmethod
    def _cx_target_unitary(qt: Any) -> Any:
        target_unitary = qt.Qobj(
            [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 0, 1],
                [0, 0, 1, 0],
            ]
        )
        target_unitary.dims = [[2, 2], [2, 2]]
        return target_unitary

    @classmethod
    def _dressed_cx_target_unitary(
        cls,
        qt: Any,
        np: Any,
        control_phase: float,
        target_phase: float,
    ) -> Any:
        def rz(theta: float) -> Any:
            return np.diag(
                [
                    np.exp(-0.5j * theta),
                    np.exp(0.5j * theta),
                ]
            )

        dressed = np.kron(rz(control_phase), rz(target_phase)) @ np.asarray(
            cls._cx_target_unitary(qt).full()
        )
        target_unitary = qt.Qobj(dressed)
        target_unitary.dims = [[2, 2], [2, 2]]
        return target_unitary

    @staticmethod
    def _computational_probabilities(result: Any) -> dict[str, float]:
        import numpy as np

        populations = np.real(result.final_state.diag())
        return {
            label: float(populations[result.system.basis_labels.index(label)])
            for label in ("00", "01", "10", "11")
        }


def filter_pulse_schedule_for_simulation(
    schedule: Any,
    *,
    labels: list[str] | tuple[str, ...] | None = None,
    active_only: bool = True,
) -> Any:
    """Return a copy of a Qubex ``PulseSchedule`` with irrelevant channels removed."""
    filtered = schedule.copy() if hasattr(schedule, "copy") else schedule
    keep = (
        set(str(label) for label in labels)
        if labels is not None
        else set(getattr(filtered, "labels", ()))
    )
    if active_only:
        pulse_ranges = filtered.get_pulse_ranges() if hasattr(filtered, "get_pulse_ranges") else {}
        active_labels = {
            label
            for label, ranges in pulse_ranges.items()
            if any(pulse_range.start != pulse_range.stop for pulse_range in ranges)
        }
        keep &= active_labels
    channels = getattr(filtered, "_channels", None)
    if isinstance(channels, dict):
        filtered._channels = {
            label: channel for label, channel in channels.items() if label in keep
        }
    offsets = getattr(filtered, "_offsets", None)
    if isinstance(offsets, dict):
        for label in list(offsets):
            if label not in keep:
                offsets.pop(label, None)
    return filtered


def materialize_pulse_schedule_for_simulation(
    schedule: Any,
    *,
    labels: list[str] | tuple[str, ...] | None = None,
) -> Any:
    """Convert a QUBEX pulse schedule into numeric waveforms for qxsimulator."""
    try:
        import numpy as np
        import qubex as qx
    except ImportError as exc:
        raise ImportError(
            "materialize_pulse_schedule_for_simulation requires qubex and numpy."
        ) from exc

    source_labels = list(labels or getattr(schedule, "labels", ()))
    schedule_labels = set(getattr(schedule, "labels", ()))
    channels = []
    final_frame_shifts: dict[str, float] = {}
    for label in source_labels:
        frequency = (
            schedule.get_frequency(label)
            if hasattr(schedule, "get_frequency") and label in schedule_labels
            else None
        )
        target = (
            schedule.get_target(label)
            if hasattr(schedule, "get_target") and label in schedule_labels
            else None
        )
        channels.append(qx.PulseChannel(label=label, frequency=frequency, target=target))
        if label in schedule_labels and hasattr(schedule, "get_final_frame_shift"):
            target_label = _simulation_target_label(target)
            frame_source = target_label if target_label in schedule_labels else label
            final_frame_shifts[label] = float(schedule.get_final_frame_shift(frame_source))

    with qx.PulseSchedule(channels) as materialized:
        for label in source_labels:
            if label not in schedule_labels:
                continue
            sequence = schedule._channels[label].sequence
            values = np.asarray(sequence.values, dtype=complex)
            values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
            materialized.add(
                label,
                qx.pulse.Arbitrary(
                    values=values,
                    sampling_period=getattr(sequence, "SAMPLING_PERIOD", None),
                ),
            )
            final_frame_shift = final_frame_shifts.get(label, 0.0)
            if abs(final_frame_shift) > 1e-12:
                materialized.add(label, qx.pulse.VirtualZ(-final_frame_shift))
    return materialized


def _simulation_target_label(target: Any) -> str | None:
    if target is None:
        return None
    if isinstance(target, str):
        return target
    label = getattr(target, "label", None)
    if label is not None:
        return str(label)
    obj = getattr(target, "object", None)
    obj_label = getattr(obj, "label", None)
    if obj_label is not None:
        return str(obj_label)
    return str(target)


def build_qxsimulator_system(
    model: str | Path | Mapping[str, Any],
    *,
    qubit_labels: list[str] | tuple[str, ...] | None = None,
    qubit_dimension: int = 3,
    include_decoherence: bool = True,
    include_resonators: bool = False,
    resonator_dimension: int = 2,
    default_coupling_strength: float | None = None,
):
    """Build a ``qxsimulator.QuantumSystem`` from a fake experiment model.

    Frequencies and anharmonicities are interpreted in GHz. Qubit lifetimes in
    ``qubit_lifetime`` are interpreted in microseconds. Coupling strengths from
    ``coupling_strength_mhz`` are converted to GHz for qxsimulator.
    """
    try:
        from qxsimulator import Coupling, QuantumSystem, Resonator, Transmon
    except ImportError as exc:
        raise ImportError("build_qxsimulator_system requires qxsimulator to be installed.") from exc

    topology = _load_model(model)
    all_qubits = list(topology.get("qubits", ()))
    qubits = list(all_qubits)
    if qubit_labels is not None:
        selected = set(str(label) for label in qubit_labels)
        qubits = [qubit for qubit in qubits if _qubit_label(qubit, all_qubits) in selected]
    if not qubits:
        raise ValueError("model must contain at least one qubit.")

    label_by_logical_id = {int(qubit["id"]): _qubit_label(qubit, all_qubits) for qubit in qubits}

    objects = []
    for qubit in qubits:
        label = _qubit_label(qubit, all_qubits)
        frequency = _required_float(qubit.get("frequency"), f"frequency for {label}")
        lifetime = qubit.get("qubit_lifetime") or {}
        relaxation_rate, dephasing_rate = _decoherence_rates(
            lifetime.get("t1"),
            lifetime.get("t2"),
            include_decoherence=include_decoherence,
        )
        objects.append(
            Transmon(
                label=label,
                dimension=qubit_dimension,
                frequency=frequency,
                anharmonicity=_optional_float(qubit.get("anharmonicity")),
                relaxation_rate=relaxation_rate,
                dephasing_rate=dephasing_rate,
            )
        )
        if include_resonators:
            resonator_frequency = _optional_float(
                qubit.get("resonator_frequency", qubit.get("readout_frequency"))
            )
            if resonator_frequency is not None:
                objects.append(
                    Resonator(
                        label=_readout_label(label),
                        dimension=resonator_dimension,
                        frequency=resonator_frequency,
                    )
                )

    couplings = []
    seen_coupling_pairs = set()
    for coupling in topology.get("couplings", ()):
        control = int(coupling["control"])
        target = int(coupling["target"])
        if control not in label_by_logical_id or target not in label_by_logical_id:
            continue
        pair = (label_by_logical_id[control], label_by_logical_id[target])
        pair_key = frozenset(pair)
        if pair_key in seen_coupling_pairs:
            continue
        strength = _coupling_strength_ghz(
            coupling,
            default_coupling_strength=default_coupling_strength,
        )
        if strength is None:
            continue
        seen_coupling_pairs.add(pair_key)
        couplings.append(Coupling(pair=pair, strength=strength))

    return QuantumSystem(objects=objects, couplings=couplings)


def _load_model(model: str | Path | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(model, Mapping):
        return model
    return json.loads(Path(model).read_text(encoding="utf-8"))


def _qubit_label(qubit: Mapping[str, Any], qubits: list[Mapping[str, Any]]) -> str:
    label = qubit.get("label")
    if label is not None:
        return str(label)
    physical_id = int(qubit.get("physical_id", qubit.get("id")))
    return _qid_to_label(physical_id, _label_width_base(qubits))


def _label_width_base(qubits: list[Mapping[str, Any]]) -> int:
    physical_ids = [
        int(qubit.get("physical_id", qubit.get("id", index))) for index, qubit in enumerate(qubits)
    ]
    return max(max(physical_ids, default=0) + 1, len(qubits))


def _readout_label(qubit_label: str) -> str:
    return f"R{qubit_label}"


def _required_float(value: Any, name: str) -> float:
    converted = _optional_float(value)
    if converted is None:
        raise ValueError(f"model is missing {name}.")
    return converted


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _decoherence_rates(
    t1_us: Any,
    t2_us: Any,
    *,
    include_decoherence: bool,
) -> tuple[float, float]:
    if not include_decoherence:
        return 0.0, 0.0
    relaxation_rate = _lifetime_rate_per_ns(t1_us)
    t2_rate = _lifetime_rate_per_ns(t2_us)
    dephasing_rate = max(0.0, t2_rate - 0.5 * relaxation_rate)
    return relaxation_rate, dephasing_rate


def _lifetime_rate_per_ns(value_us: Any) -> float:
    value = _optional_float(value_us)
    if value is None or value <= 0.0:
        return 0.0
    return 1.0 / (value * 1000.0)


def _coupling_strength_ghz(
    coupling: Mapping[str, Any],
    *,
    default_coupling_strength: float | None,
) -> float | None:
    if coupling.get("coupling_strength_mhz") is not None:
        return float(coupling["coupling_strength_mhz"]) / 1000.0
    if coupling.get("coupling_strength") is not None:
        return float(coupling["coupling_strength"])
    return default_coupling_strength


def _simulation_dependencies() -> tuple[Any, ...]:
    try:
        import numpy as np
        import pandas as pd
        import qutip as qt
        import qubex as qx
        from qubex.experiment.models.result import Result
        from qubex.measurement.classifiers.state_classifier_gmm import (
            StateClassifierGMM,
        )
        from qxsimulator import Control, QuantumSimulator
    except ImportError as exc:
        raise ImportError(
            "FakeExperiment calibration methods require qubex, qutip, "
            "qxsimulator, numpy, and pandas to be installed."
        ) from exc
    return np, pd, qx, qt, Result, StateClassifierGMM, Control, QuantumSimulator


_UNSUPPORTED_EXPERIMENT_METHODS = {
    "create_entangle_sequence",
    "create_ghz_sequence",
    "measure_ghz_state",
    "ghz_state_tomography",
    "create_mqc_sequence",
    "mqc_experiment",
    "fourier_analysis",
    "parity_oscillation",
    "create_1d_cluster_sequence",
    "measure_1d_cluster_state",
    "partial_transpose",
    "create_connected_graphs",
    "create_maximum_graph",
    "create_maximum_1d_chain",
    "create_maximum_spanning_tree",
    "create_maximum_directed_tree",
    "create_cz_rounds",
    "create_graph_sequence",
    "create_measurement_rounds",
    "visualize_graph",
    "measure_graph_state",
    "measure_bell_state_fidelities",
    "measure_bell_states",
    "measure_electrical_delay",
    "scan_resonator_frequencies",
    "resonator_spectroscopy",
    "measure_reflection_coefficient",
    "scan_qubit_frequencies",
    "estimate_control_amplitude",
    "measure_qubit_resonance",
    "qubit_spectroscopy",
    "measure_dispersive_shift",
    "find_optimal_readout_frequency",
    "find_optimal_readout_amplitude",
    "ckp_sequence",
    "ckp_measurement",
    "ckp_experiment",
}
