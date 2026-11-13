"""Qibocal ``rabi_amplitude`` on a Qibolab emulator."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import plotly.io as pio

from qdash.common.qibocal_platform import CALIBRATION_FIELDS
from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qibocal.base import QibocalTask
from qdash.workflow.engine.backend.qibocal import QibocalRequest, QibocalRunResult

if TYPE_CHECKING:
    import plotly.graph_objs as go

    from qdash.workflow.engine.backend.qibocal import QibocalBackend


class QibocalRabiAmplitude(QibocalTask):
    """Find the pi-pulse amplitude with Qibocal's ``rabi_amplitude`` on an emulator.

    Acquisition, fit, and figure are Qibocal's own; QDash converts the runner result into
    task outputs. The sweep must start above zero: at zero amplitude the excited-state
    probability is exactly zero, its binomial error is zero, and Qibocal's weighted fit
    fails.

    The task fails, keeping its figure and raw data, when Qibocal reports no fit, when the
    amplitude, its error, chi-squared, or a fitted parameter is not finite, or when the
    amplitude lies outside the swept range.
    """

    name: str = "QibocalRabiAmplitude"
    task_type: str = "qubit"
    chi2_parameter: ClassVar[str] = "qibocal_rabi_chi2"

    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "qibocal_qubit_frequency": InputParameterSpec.required_database(
            unit="GHz", description="Native Qibolab drive frequency"
        ),
        "qibocal_pi_duration": InputParameterSpec.required_database(
            unit="ns", description="Native RX and RX90 pulse duration"
        ),
        "qibocal_pi_amplitude": InputParameterSpec.required_database(
            unit="a.u.", description="Native RX pulse amplitude; RX90 uses half"
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "min_amp": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=0.01,
            description="First drive amplitude of the sweep; must be greater than 0",
        ),
        "max_amp": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=0.5,
            description="Last drive amplitude of the sweep",
        ),
        "step_amp": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=0.01,
            description="Drive amplitude step",
        ),
        "nshots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=1024,
            description="Number of single shots per amplitude",
        ),
        "relaxation_time": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=0.0,
            description="Wait time between shots",
        ),
        "seed": RunParameterSpec(
            unit="",
            value_type="int",
            default=1234,
            description="NumPy seed of the emulator run, for reproducible results",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qibocal_pi_duration": OutputParameterSpec(
            unit="ns", description="Duration paired with the fitted native RX amplitude"
        ),
        "qibocal_pi_amplitude": OutputParameterSpec(
            unit="a.u.",
            description="Pi-pulse drive amplitude fitted by Qibocal on the Qibolab emulator",
        ),
        "qibocal_rabi_chi2": OutputParameterSpec(
            unit="",
            description="Reduced chi-squared of Qibocal's Rabi amplitude fit",
        ),
    }

    def _run_value(self, name: str) -> Any:
        return self.run_parameters[name].get_value()

    def build_request(self, qid: str) -> QibocalRequest:
        """Validate the sweep and build the runner request."""
        min_amp = float(self._run_value("min_amp"))
        max_amp = float(self._run_value("max_amp"))
        step_amp = float(self._run_value("step_amp"))
        nshots = int(self._run_value("nshots"))
        relaxation_time = float(self._run_value("relaxation_time"))
        seed = int(self._run_value("seed"))
        if not all(math.isfinite(v) for v in (min_amp, max_amp, step_amp, relaxation_time)):
            raise ValueError("Sweep values must be finite")
        if min_amp <= 0:
            raise ValueError(
                "min_amp must be greater than 0: at zero amplitude Qibocal's weighted fit "
                "has a zero error and fails"
            )
        if max_amp <= min_amp:
            raise ValueError("max_amp must be greater than min_amp")
        if max_amp > 1:
            raise ValueError("max_amp must not exceed 1")
        if step_amp <= 0 or (max_amp - min_amp) / step_amp < 4:
            raise ValueError("step_amp must be positive and give at least 5 sweep points")
        if nshots <= 0:
            raise ValueError("nshots must be positive")
        if relaxation_time < 0:
            raise ValueError("relaxation_time must not be negative")
        return QibocalRequest(
            qubit=int(qid),
            protocol="rabi_amplitude",
            parameters={
                "min_amp": min_amp,
                "max_amp": max_amp,
                "step_amp": step_amp,
                "nshots": nshots,
                "relaxation_time": relaxation_time,
            },
            seed=seed,
            calibration={
                field.name: field.validate(self.input_parameters[field.name].value)
                for field in CALIBRATION_FIELDS
            },
        )

    def run(self, backend: QibocalBackend, qid: str) -> RunResult:
        """Run Qibocal ``rabi_amplitude`` through the isolated runner."""
        request = self.build_request(qid)
        runner = backend.get_instance()
        self.output_provenance = {
            "source": "qibolab-emulator",
            "synthetic": True,
            "chip_id": backend.config["chip_id"],
            "project_id": backend.config.get("project_id"),
            "simulation_binding": backend.binding().model_dump(mode="json"),
            "calibration": request.calibration,
            "protocol": request.protocol,
        }
        try:
            result = runner.run_protocol(request, label=f"{self.name}_q{qid}")
        finally:
            self.output_provenance["run_dir"] = str(getattr(runner, "last_run_dir", ""))
        self.output_provenance.update(result.provenance)
        return RunResult(raw_result=result)

    def extract_raw_data(self, run_result: RunResult) -> list[Any]:
        """Return the acquired probabilities and their errors against amplitude."""
        from qdash.common.raw_data import PreFitRawData

        result: QibocalRunResult = run_result.raw_result
        data = result.result["data"]
        amplitude = np.asarray(data["amplitude"], dtype=float)
        protocol = result.result["protocol"]
        axis = "amplitude" if protocol == "rabi_amplitude" else "flips"
        target = f"Q{result.result['qubit']}"
        return [
            PreFitRawData(
                target=target,
                data=np.asarray(data["probability"], dtype=float),
                axes={axis: amplitude},
                source_type=f"qibocal.{protocol}.probability",
            ),
            PreFitRawData(
                target=target,
                data=np.asarray(data["error"], dtype=float),
                axes={axis: amplitude},
                source_type=f"qibocal.{protocol}.probability_error",
            ),
        ]

    def fit_errors(self, result: QibocalRunResult) -> list[str]:
        """Return why the Qibocal fit cannot be reported, or an empty list."""
        fit = result.fit
        errors = list(fit.get("errors") or [])
        if fit.get("status") != "ok" and not errors:
            errors.append("Qibocal fit failed")
        amplitude = fit.get("pi_amplitude")
        request = result.result.get("request", {}).get("parameters", {})
        if not errors and amplitude is not None and result.result["protocol"] == "rabi_amplitude":
            low, high = float(request["min_amp"]), float(request["max_amp"])
            if not low <= float(amplitude) <= high:
                errors.append(
                    f"Qibocal pi-pulse amplitude {amplitude:.6g} is outside the swept "
                    f"range [{low:g}, {high:g}]"
                )
        for name in ("pi_amplitude", "pi_amplitude_error", "pulse_length", "chi2", "chi2_error"):
            value = fit.get(name)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"Invalid fitted {name}")
        if amplitude is not None and not 0 < float(amplitude) <= 1:
            errors.append("Fitted amplitude is outside (0, 1]")
        fitted = fit.get("fitted_parameters")
        if (
            not isinstance(fitted, list)
            or not fitted
            or any(
                not isinstance(value, (int, float)) or not math.isfinite(value) for value in fitted
            )
        ):
            errors.append("Qibocal fitted parameters are missing or not finite")
        duration = fit.get("pulse_length")
        if isinstance(duration, (int, float)) and duration <= 0:
            errors.append("Fitted pulse duration must be positive")
        return errors

    def postprocess(
        self, backend: QibocalBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        """Convert the runner result into outputs, Qibocal's figure, and provenance."""
        result: QibocalRunResult = run_result.raw_result
        fit = result.fit
        provenance = result.provenance
        self.output_provenance = {
            **provenance,
            "source": provenance["source"],
            "synthetic": True,
            "backend": "qibocal",
            "protocol": result.result["protocol"],
            "controllers": provenance["controllers"],
            "platform": provenance["platform"],
            "platform_sha256": provenance["platform_sha256_before"],
            "executor_update": provenance["executor_update"],
            "seed": provenance["seed"],
            "versions": provenance["versions"],
            "runner_lock_sha256": provenance.get("runner_lock_sha256"),
            "runner_script_sha256": provenance.get("runner_script_sha256"),
            "run_dir": str(result.run_dir),
        }

        figures = self._figures(result, qid)
        errors = self.fit_errors(result)
        if errors:
            return PostProcessResult(
                output_parameters={},
                figures=figures,
                validation_error="; ".join(errors),
            )

        self.output_parameters["qibocal_pi_duration"].value = float(fit["pulse_length"])
        self.output_parameters["qibocal_pi_amplitude"].value = float(fit["pi_amplitude"])
        self.output_parameters["qibocal_pi_amplitude"].error = float(fit["pi_amplitude_error"])
        self.output_parameters[self.chi2_parameter].value = float(fit["chi2"])
        self.output_parameters[self.chi2_parameter].error = float(fit["chi2_error"] or 0.0)
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=figures,
        )

    @staticmethod
    def _figures(result: QibocalRunResult, qid: str) -> list[go.Figure]:
        """Load Qibocal's report figures and label them as emulator results."""
        figures: list[go.Figure] = []
        for path in result.result.get("figures", []):
            figure = pio.read_json(path)
            figure.update_layout(
                title={
                    "text": f"Qibocal {result.result['protocol']} : Q{qid} (Qibolab emulator, synthetic)",
                    "x": 0.5,
                },
            )
            figures.append(figure)
        return figures
