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
        "qubit_frequency": InputParameterSpec.required_database(
            unit="GHz", greater_than=0, description="Calibrated GE control frequency"
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
        # Keep task-specific effective-input constraints for values that
        # directly determine the restored Rabi context.
        "control_amplitude": InputParameterSpec.required_database(
            unit="a.u.", greater_than=0, less_than=1, description="Rabi control amplitude"
        ),
        "rabi_r2": InputParameterSpec.required_database(
            unit="", greater_than_or_equal=0.6, description="Rabi-fit R²"
        ),
        "maximum_rabi_frequency": InputParameterSpec.required_database(
            unit="MHz/a.u.",
            greater_than=0,
            description="Maximum Rabi frequency per control amplitude",
        ),
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
        "qubit_drive_scale": RunParameterSpec(
            unit="", value_type="float", default=0.8, description="Relative CKP qubit-drive area"
        ),
        "qubit_drive_duration": RunParameterSpec(
            unit="ns", value_type="float", default=128.0, description="CKP qubit-drive duration"
        ),
        "resonator_settle_duration": RunParameterSpec(
            unit="ns", value_type="float", default=512.0, description="Resonator settling time"
        ),
        "shots": RunParameterSpec(
            unit="a.u.", value_type="int", default=1024, description="Shots per CKP point"
        ),
        "interval": RunParameterSpec(
            unit="ns", value_type="int", default=153600, description="Shot interval"
        ),
        "enable_rough_search": RunParameterSpec(
            unit="",
            value_type="bool",
            default=True,
            description="Adjust drive amplitude before CKP",
        ),
        "target_min_qubit_detuning": RunParameterSpec(
            unit="GHz",
            value_type="float",
            default=-0.02,
            description="Target minimum Stark-shift detuning during rough search",
        ),
        "max_rough_search_reductions": RunParameterSpec(
            unit="a.u.", value_type="int", default=4, description="Maximum rough-search reductions"
        ),
        "max_rough_search_increases": RunParameterSpec(
            unit="a.u.", value_type="int", default=4, description="Maximum rough-search increases"
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

    def _rough_search_options(self) -> tuple[bool, float, int, int]:
        enabled = bool(self.run_parameters["enable_rough_search"].get_value())
        target = float(self.run_parameters["target_min_qubit_detuning"].get_value())
        reductions = int(self.run_parameters["max_rough_search_reductions"].get_value())
        increases = int(self.run_parameters["max_rough_search_increases"].get_value())
        if reductions < 0 or increases < 0:
            raise ValueError("Rough-search trial limits must be non-negative")
        if enabled and (not math.isfinite(target) or target >= 0):
            raise ValueError("target_min_qubit_detuning must be finite and negative")
        return enabled, target, reductions, increases

    def get_progress_plan(self) -> ProgressPlan:
        """Report four fixed CKP scans plus bounded rough-search sweeps."""
        enabled, _, reductions, increases = self._rough_search_options()
        if not enabled:
            return ProgressPlan(4, 4)
        # A reduction/increase limit terminates the rough-search loop on its
        # final trial.  When both limits are nonzero, at most one can reach
        # its limit, hence ``reductions + increases - 1`` attempts.  A rough
        # CKP measurement may add one refinement sweep after its primary
        # sweep, so each attempt accounts for up to two progress phases.
        rough_attempts_max = max(1, reductions, increases, reductions + increases - 1)
        return ProgressPlan(5, 4 + 2 * rough_attempts_max)

    def _run_kwargs(self) -> dict[str, Any]:
        qubit_drive_scale = float(self.run_parameters["qubit_drive_scale"].get_value())
        qubit_drive_duration = float(self.run_parameters["qubit_drive_duration"].get_value())
        resonator_settle_duration = float(
            self.run_parameters["resonator_settle_duration"].get_value()
        )
        n_shots = int(self.run_parameters["shots"].get_value())
        interval = float(self.run_parameters["interval"].get_value())
        if not math.isfinite(qubit_drive_scale) or qubit_drive_scale <= 0:
            raise ValueError("qubit_drive_scale must be finite and positive")
        if not math.isfinite(qubit_drive_duration) or qubit_drive_duration <= 0:
            raise ValueError("qubit_drive_duration must be finite and positive")
        if not math.isfinite(resonator_settle_duration) or resonator_settle_duration <= 0:
            raise ValueError("resonator_settle_duration must be finite and positive")
        if n_shots <= 0 or not math.isfinite(interval) or interval <= 0:
            raise ValueError("shots and interval must be finite and positive")

        rough_enabled, rough_target, reductions, increases = self._rough_search_options()
        return {
            "control_frequency": self._get_calibration_value("qubit_frequency"),
            "readout_frequency": self._get_calibration_value("readout_frequency"),
            "readout_amplitude": self._get_calibration_value("readout_amplitude"),
            "qubit_detuning_range": self._optional_sweep("qubit_detuning_range"),
            "qubit_drive_scale": qubit_drive_scale,
            "qubit_drive_duration": qubit_drive_duration,
            "resonator_detuning_range": self._optional_sweep("resonator_detuning_range"),
            "resonator_settle_duration": resonator_settle_duration,
            "n_shots": n_shots,
            "shot_interval": interval,
            "plot": False,
            "save_image": False,
            "enable_rough_search": rough_enabled,
            "target_min_qubit_detuning": rough_target,
            "max_rough_search_reductions": reductions,
            "max_rough_search_increases": increases,
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
