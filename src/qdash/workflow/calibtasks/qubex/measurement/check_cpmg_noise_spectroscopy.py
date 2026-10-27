"""CPMG noise spectroscopy task."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import numpy.typing as npt
from qubex.core import DataModel
from qubex.experiment.experiment_constants import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    required_rabi_normalization_inputs,
)

if TYPE_CHECKING:
    import plotly.graph_objects as go

    from qdash.workflow.engine.backend.qubex import QubexBackend


CPMG_PATTERNS = ("++++", "+--+", "+-+-")


class CPMGNoiseSpectroscopyData(DataModel):
    """NetCDF artifact containing CPMG measurements and fit diagnostics."""

    schema_version: int
    timestamp: str
    target: str
    n_repeats: int
    requested_frequency_range: npt.NDArray[Any]
    realized_frequency_range: npt.NDArray[Any]
    valid_frequency_mask: npt.NDArray[Any]
    half_tau_range: npt.NDArray[Any]
    requested_time_range: npt.NDArray[Any]
    t2_matrix: npt.NDArray[Any]
    t2_error_matrix: npt.NDArray[Any]
    gamma2_matrix: npt.NDArray[Any]
    gamma2_error_matrix: npt.NDArray[Any]
    r2_matrix: npt.NDArray[Any]
    fit_records: tuple[dict[str, Any], ...]
    frequency_plan: tuple[dict[str, Any], ...]
    acquisition_orders: npt.NDArray[Any]
    random_seed: int
    random_seed_requested: int | None
    metadata: dict[str, Any]
    failed_fits: tuple[dict[str, Any], ...]


class CheckCPMGNoiseSpectroscopy(QubexTask):
    """Measure CPMG coherence over an effective noise-frequency sweep."""

    name: str = "CheckCPMGNoiseSpectroscopy"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        **required_rabi_normalization_inputs(),
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",),
            unit="GHz",
            greater_than=0,
            description="Calibrated GE control frequency",
        ),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",),
            unit="GHz",
            greater_than=0,
            description="Calibrated readout frequency",
        ),
        "readout_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            less_than_or_equal=1,
            description="Calibrated readout amplitude",
        ),
        "hpi_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            description="Calibrated half-pi pulse amplitude",
        ),
        "hpi_duration": InputParameterSpec.required_database(
            unit="ns",
            greater_than=0,
            description="Calibrated half-pi pulse duration",
        ),
        "pi_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            description="Fallback non-DRAG pi pulse amplitude",
        ),
        "pi_duration": InputParameterSpec.required_database(
            parameter_aliases=("pi_length",),
            unit="ns",
            greater_than=0,
            description="Fallback non-DRAG pi pulse duration",
        ),
        "drag_pi_amplitude": InputParameterSpec.database_or_default(
            default=0,
            unit="a.u.",
            greater_than_or_equal=0,
            description="Optional calibrated DRAG pi pulse amplitude",
        ),
        "drag_pi_duration": InputParameterSpec.database_or_default(
            default=0,
            parameter_aliases=("drag_pi_length",),
            unit="ns",
            greater_than_or_equal=0,
            description="Optional calibrated DRAG pi pulse duration",
        ),
        "drag_pi_beta": InputParameterSpec.database_or_default(
            default=0,
            unit="a.u.",
            description="Optional calibrated DRAG pi correction coefficient",
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "frequency_range": RunParameterSpec(
            unit="GHz",
            value_type="np.linspace",
            default=(0.0005, 0.004, 20),
            description="Requested effective CPMG frequency sweep",
        ),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="np.logspace",
            default=(np.log10(200.0), np.log10(200_000.0), 31),
            description="Requested CPMG decay-time sweep",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=DEFAULT_SHOTS,
            description="Shots per CPMG decay point",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Interval between shots",
        ),
        "pi_pulse_pattern": RunParameterSpec(
            value_type="str",
            default="++++",
            description="CPMG pi-pulse sign pattern: ++++, +--+, or +-+-",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {}

    def _positive_range(self, name: str) -> np.ndarray:
        """Return one validated positive one-dimensional sweep."""
        values = np.asarray(self.run_parameters[name].get_value(), dtype=float)
        if values.ndim != 1 or values.size == 0:
            raise ValueError(f"{name} must be a non-empty 1D array")
        if not np.isfinite(values).all() or np.any(values <= 0):
            raise ValueError(f"{name} must contain positive finite values")
        return values

    def _run_kwargs(self) -> dict[str, Any]:
        """Return validated options passed directly to Qubex."""
        shots = int(self.run_parameters["shots"].get_value())
        interval = float(self.run_parameters["interval"].get_value())
        pattern = str(self.run_parameters["pi_pulse_pattern"].get_value())
        if shots <= 0:
            raise ValueError("shots must be positive")
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval must be finite and positive")
        if pattern not in CPMG_PATTERNS:
            raise ValueError("pi_pulse_pattern must be one of '++++', '+--+', or '+-+-'")
        return {
            "frequency_range": self._positive_range("frequency_range"),
            "time_range": self._positive_range("time_range"),
            "pi_pulse_pattern": pattern,
            "n_shots": shots,
            "shot_interval": interval,
            "plot": False,
            "save_image": False,
            "save_data": False,
        }

    def _has_drag_pi_calibration(self) -> bool:
        """Return whether the optional QDash DRAG PI group is usable."""
        amplitude = self._get_calibration_value("drag_pi_amplitude")
        duration = self._get_calibration_value("drag_pi_duration")
        beta = self._get_calibration_value("drag_pi_beta")
        return (
            math.isfinite(amplitude)
            and amplitude > 0
            and math.isfinite(duration)
            and duration > 0
            and math.isfinite(beta)
        )

    def _cpmg_pi_pulse(self, exp: Any, label: str) -> Any:
        """Return a Y-axis DRAG PI when available, otherwise a plain Y PI."""
        pulse = exp.drag_pi_pulse[label] if self._has_drag_pi_calibration() else exp.pi_pulse[label]
        return pulse.shifted(np.pi / 2)

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run one-target CPMG noise spectroscopy without Qubex file output."""
        from qubex.contrib import cpmg_noise_spectroscopy

        run_options = self._run_kwargs()
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        resonator_label = self.get_resonator_label(backend, qid)
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")
        pi_pulses = {label: self._cpmg_pi_pulse(exp, label)}
        with exp.modified_frequencies(
            {
                label: self._get_calibration_value("control_frequency"),
                resonator_label: self._get_calibration_value("readout_frequency"),
            }
        ):
            result = cpmg_noise_spectroscopy(
                exp,
                targets=[label],
                pi_pulses=pi_pulses,
                **run_options,
            )
        return RunResult(raw_result=result)

    @staticmethod
    def _mapping(value: Any, name: str) -> Mapping[str, Any]:
        """Return a required Qubex result mapping."""
        if not isinstance(value, Mapping):
            raise TypeError(f"CPMG result field {name!r} must be a mapping")
        return value

    @classmethod
    def _target_payload(cls, result: Any) -> tuple[str, Mapping[str, Any]]:
        """Return the sole target and validated Qubex result payload."""
        data = cls._mapping(result.data, "data")
        targets = data.get("targets")
        if not isinstance(targets, list) or len(targets) != 1:
            raise ValueError("CPMG result must contain exactly one target")
        return str(targets[0]), data

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Build a NetCDF artifact retaining CPMG curves and fit diagnostics."""
        target, data = self._target_payload(run_result.raw_result)
        time_range = data.get("time_range")
        if time_range is None:
            raise ValueError("CPMG result is missing time_range")
        artifact = CPMGNoiseSpectroscopyData(
            schema_version=int(data["schema_version"]),
            timestamp=str(data["timestamp"]),
            target=target,
            n_repeats=int(data["n_repeats"]),
            requested_frequency_range=np.asarray(data["frequency_range"]),
            realized_frequency_range=np.asarray(data["realized_frequency_matrix"])[0],
            valid_frequency_mask=np.asarray(data["valid_frequency_mask"], dtype=bool)[0],
            half_tau_range=np.asarray(data["half_tau_range"]),
            requested_time_range=np.asarray(time_range),
            t2_matrix=np.asarray(data["t2_matrix"])[0],
            t2_error_matrix=np.asarray(data["t2_error_matrix"])[0],
            gamma2_matrix=np.asarray(data["gamma2_matrix"])[0],
            gamma2_error_matrix=np.asarray(data["gamma2_error_matrix"])[0],
            r2_matrix=np.asarray(data["r2_matrix"])[0],
            fit_records=tuple(dict(record) for record in data["fit_records"]),
            frequency_plan=tuple(dict(point) for point in data["frequency_plans"][0]),
            acquisition_orders=np.asarray(data["acquisition_orders"])[0],
            random_seed=int(data["random_seed"]),
            random_seed_requested=(
                None
                if data.get("random_seed_requested") is None
                else int(data["random_seed_requested"])
            ),
            metadata=dict(data["metadata"]),
            failed_fits=tuple(dict(failure) for failure in data["failed_fits"]),
        )
        return [artifact]

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Retain summary and heatmap figures and require one successful fit."""
        del backend, execution_id, qid
        result = run_result.raw_result
        target, data = self._target_payload(result)
        figures_by_name = result.figures or {}
        summary = figures_by_name.get("summary")
        if summary is None:
            summary = result.figure
        heatmap = figures_by_name.get(f"{target}_raw_data_heatmap")
        figures: list[go.Figure] = [figure for figure in (summary, heatmap) if figure is not None]
        gamma2 = np.asarray(data["gamma2_matrix"], dtype=float)
        validation_error = None
        if not np.any(np.isfinite(gamma2) & (gamma2 > 0)):
            validation_error = f"CPMG fit failed at all frequencies for {target}."
        return PostProcessResult(
            output_parameters={},
            figures=figures,
            validation_error=validation_error,
        )
