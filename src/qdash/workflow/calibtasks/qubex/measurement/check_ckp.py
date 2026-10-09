"""Filtered-CKP readout-chain characterization task."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from qdash.datamodel.task import (
    InputParameterSpec,
    OutputParameterSpec,
    RunParameterSpec,
)
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    readout_duration_run_parameter,
    required_rabi_normalization_inputs,
)
from qdash.workflow.calibtasks.qubex.validation import finite_value_error, first_validation_error
from qdash.workflow.engine.progress import ProgressPlan

if TYPE_CHECKING:
    from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckCKP(QubexTask):
    """Estimate readout-resonator and Purcell-filter parameters with filtered CKP."""

    name: str = "CheckCKP"
    task_type: str = "qubit"

    # ``filtered_ckp_experiment`` normalizes IQ data with the stored Rabi fit,
    # and builds the |1> preparation pulse from the calibrated HPI pulse.
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",),
            unit="GHz",
            greater_than=0,
            description="Calibrated GE control frequency",
        ),
        "readout_frequency": InputParameterSpec.required_database(
            unit="GHz", greater_than=0, description="Readout-frequency sweep center"
        ),
        "readout_amplitude": InputParameterSpec.required_database(
            unit="a.u.",
            greater_than=0,
            less_than_or_equal=1,
            description="Reference readout amplitude",
        ),
        "hpi_amplitude": InputParameterSpec.required_database(
            unit="a.u.", greater_than=0, description="Calibrated half-pi pulse amplitude"
        ),
        "hpi_duration": InputParameterSpec.required_database(
            unit="ns", greater_than=0, description="Calibrated half-pi pulse duration"
        ),
        # Qubex normalizes CKP IQ data with the persisted Rabi fit.
        **required_rabi_normalization_inputs(),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "qubit_detuning_range": RunParameterSpec(
            unit="GHz",
            value_type="list",
            default=None,
            description="Qubit-frequency offsets. Uses Qubex's CKP default when unset.",
        ),
        "resonator_detuning_range": RunParameterSpec(
            unit="GHz",
            value_type="list",
            default=None,
            description="Readout-frequency offsets. Uses Qubex's CKP default when unset.",
        ),
        "shots": RunParameterSpec(
            unit="a.u.", value_type="int", default=1024, description="Shots per CKP point"
        ),
        "interval": RunParameterSpec(
            unit="ns", value_type="int", default=153600, description="Shot interval"
        ),
        "target_min_qubit_detuning": RunParameterSpec(
            unit="GHz",
            value_type="float",
            default=-0.02,
            description="Target minimum Stark-shift detuning during rough search",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "resonator_frequency": OutputParameterSpec(
            unit="GHz", description="Ground-state readout-resonator frequency (ωr_g)"
        ),
        "readout_frequency": OutputParameterSpec(
            unit="GHz", description="Photon-limited optimal readout frequency"
        ),
        "purcell_filter_frequency": OutputParameterSpec(
            unit="GHz", description="Purcell-filter resonance frequency (ωp)"
        ),
        "resonator_purcell_filter_coupling": OutputParameterSpec(
            unit="MHz", description="Resonator--Purcell-filter coupling (J)"
        ),
        "purcell_filter_linewidth": OutputParameterSpec(
            unit="MHz", description="Purcell-filter linewidth (κ)"
        ),
        "dispersive_shift": OutputParameterSpec(unit="MHz", description="Dispersive shift (χ)"),
        "critical_photon_number": OutputParameterSpec(
            unit="a.u.", description="Estimated critical photon number"
        ),
    }

    def _optional_sweep(self, name: str) -> np.ndarray | None:
        parameter = self.run_parameters[name]
        if parameter.value is None:
            return None
        values = np.asarray(parameter.get_value(), dtype=float)
        if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
            raise ValueError(f"{name} must contain finite values")
        return values

    def get_progress_plan(self) -> ProgressPlan:
        """Return the progress range for Qubex's default rough search."""
        return ProgressPlan(5, 18)

    def _run_kwargs(self) -> dict[str, Any]:
        n_shots = int(self.run_parameters["shots"].get_value())
        interval = float(self.run_parameters["interval"].get_value())
        if n_shots <= 0 or not math.isfinite(interval) or interval <= 0:
            raise ValueError("shots and interval must be finite and positive")
        target_min_qubit_detuning = float(
            self.run_parameters["target_min_qubit_detuning"].get_value()
        )
        if not math.isfinite(target_min_qubit_detuning) or target_min_qubit_detuning >= 0:
            raise ValueError("target_min_qubit_detuning must be finite and negative")
        return {
            "control_frequency": self._get_calibration_value("control_frequency"),
            "readout_frequency": self._get_calibration_value("readout_frequency"),
            "readout_amplitude": self._get_calibration_value("readout_amplitude"),
            "qubit_detuning_range": self._optional_sweep("qubit_detuning_range"),
            "resonator_detuning_range": self._optional_sweep("resonator_detuning_range"),
            "n_shots": n_shots,
            "shot_interval": interval,
            "plot": False,
            "save_image": False,
            "target_min_qubit_detuning": target_min_qubit_detuning,
        }

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        """Run the single-qubit filtered CKP experiment without displaying figures."""
        import qubex

        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        result = qubex.contrib.filtered_ckp_experiment(
            exp,
            target=label,
            **self._run_kwargs(),
        )
        r2 = result.data.get("r2")
        return RunResult(raw_result=result, r2={qid: None if r2 is None else float(r2)})

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Convert CKP units and expose figures for QDash artifact persistence."""
        result = run_result.raw_result
        data = result.data
        values = {
            "resonator_frequency": data["omega_r_g"],
            "readout_frequency": data["optimal_readout_frequency"],
            "purcell_filter_frequency": data["omega_p"],
            "resonator_purcell_filter_coupling": 1000.0 * data["J"],
            "purcell_filter_linewidth": 1000.0 * data["kappa"],
            "dispersive_shift": 1000.0 * data["chi"],
            "critical_photon_number": data["n_crit"],
        }
        for name, value in values.items():
            self.output_parameters[name].value = value

        figures_by_name = getattr(result, "figures", {})
        figures = [
            figures_by_name[name]
            for name in ("ckp_fit", "ckp_heatmap_g", "ckp_heatmap_e", "readout_optimization")
            if figures_by_name.get(name) is not None
        ]
        if not figures and getattr(result, "figure", None) is not None:
            figures = [result.figure]

        r2 = run_result.r2.get(qid) if run_result.r2 is not None else None
        r2_validation_error = finite_value_error(r2, "Filtered CKP fit R²", maximum=1.0)
        if (
            r2_validation_error is None
            and r2 is not None
            and self.r2_is_lower_than_threshold(float(r2))
        ):
            r2_validation_error = (
                f"Filtered CKP fit R² must be greater than {self.r2_threshold}: {r2}"
            )
        validation_error = first_validation_error(
            r2_validation_error,
            finite_value_error(values["resonator_frequency"], "resonator_frequency", minimum=0.0),
            finite_value_error(values["readout_frequency"], "readout_frequency", minimum=0.0),
            finite_value_error(
                values["purcell_filter_frequency"], "purcell_filter_frequency", minimum=0.0
            ),
            finite_value_error(
                values["resonator_purcell_filter_coupling"],
                "resonator_purcell_filter_coupling",
                minimum=0.0,
            ),
            finite_value_error(
                values["purcell_filter_linewidth"], "purcell_filter_linewidth", minimum=0.0
            ),
            finite_value_error(values["dispersive_shift"], "dispersive_shift"),
            finite_value_error(
                values["critical_photon_number"], "critical_photon_number", minimum=0.0
            ),
        )
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=figures,
            validation_error=validation_error,
        )
