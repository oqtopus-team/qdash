"""Measure static ZZ with Qubex JAZZ and conditionally estimate coupling strength."""

import math
from typing import Any, ClassVar

import numpy as np
from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    readout_duration_run_parameter,
    required_rabi_normalization_inputs,
)
from qdash.workflow.calibtasks.qubex.validation import finite_value_error, first_validation_error
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckCouplingStrength(QubexTask):
    """Measure JAZZ and estimate coupling strength when both anharmonicities are known.

    The first qid is the measured/control qubit and the second is the spectator/target qubit.
    Frequencies and anharmonicities used by the estimate are resolved from QDash calibration
    inputs rather than from Qubex's implicit anharmonicity fallback.
    """

    name: str = "CheckCouplingStrength"
    task_type: str = "coupling"
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "time_range": RunParameterSpec(
            unit="ns",
            value_type="np.arange",
            default=(0, 20001, 400),
            description="Wait time in each half of the JAZZ echo sequence",
        ),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Number of shots",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="int",
            default=DEFAULT_INTERVAL,
            description="Time interval between shots",
        ),
    }

    # Input parameters from control and target qubits
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        **required_rabi_normalization_inputs(prefix="control_", qid_role="control"),
        "control_qubit_frequency": InputParameterSpec.required_database(
            parameter_name="control_frequency",
            qid_role="control",
            unit="GHz",
            fallback_parameter_names=("qubit_frequency",),
            greater_than=0,
            description="Calibrated GE frequency of the measured/control qubit",
        ),
        "control_qubit_anharmonicity": InputParameterSpec.database_optional(
            parameter_name="qubit_anharmonicity",
            parameter_aliases=("anharmonicity",),
            qid_role="control",
            unit="GHz",
            less_than=0,
            user_override="forbidden",
            description="Optional calibrated anharmonicity of the measured/control qubit",
        ),
        "control_hpi_amplitude": InputParameterSpec.required_database(
            parameter_name="hpi_amplitude",
            qid_role="control",
            unit="a.u.",
            greater_than=0,
        ),
        "control_hpi_duration": InputParameterSpec.required_database(
            parameter_name="hpi_duration",
            qid_role="control",
            unit="ns",
            greater_than=0,
        ),
        "control_readout_frequency": InputParameterSpec.required_database(
            parameter_name="readout_frequency",
            qid_role="control",
            unit="GHz",
            fallback_parameter_names=("resonator_frequency",),
            greater_than=0,
        ),
        "control_readout_amplitude": InputParameterSpec.required_database(
            parameter_name="readout_amplitude",
            qid_role="control",
            unit="a.u.",
            greater_than=0,
            less_than_or_equal=1,
        ),
        **required_rabi_normalization_inputs(prefix="target_", qid_role="target"),
        "target_qubit_frequency": InputParameterSpec.required_database(
            parameter_name="control_frequency",
            qid_role="target",
            unit="GHz",
            fallback_parameter_names=("qubit_frequency",),
            greater_than=0,
            description="Calibrated GE frequency of the spectator/target qubit",
        ),
        "target_qubit_anharmonicity": InputParameterSpec.database_optional(
            parameter_name="qubit_anharmonicity",
            parameter_aliases=("anharmonicity",),
            qid_role="target",
            unit="GHz",
            less_than=0,
            user_override="forbidden",
            description="Optional calibrated anharmonicity of the spectator/target qubit",
        ),
        "target_hpi_amplitude": InputParameterSpec.required_database(
            parameter_name="hpi_amplitude",
            qid_role="target",
            unit="a.u.",
            greater_than=0,
        ),
        "target_hpi_duration": InputParameterSpec.required_database(
            parameter_name="hpi_duration",
            qid_role="target",
            unit="ns",
            greater_than=0,
        ),
        "target_readout_frequency": InputParameterSpec.required_database(
            parameter_name="readout_frequency",
            qid_role="target",
            unit="GHz",
            fallback_parameter_names=("resonator_frequency",),
            greater_than=0,
        ),
        "target_readout_amplitude": InputParameterSpec.required_database(
            parameter_name="readout_amplitude",
            qid_role="target",
            unit="a.u.",
            greater_than=0,
            less_than_or_equal=1,
        ),
    }

    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "static_zz_interaction": OutputParameterSpec(
            qid_role="coupling",
            unit="KHz",
            description="Signed static ZZ interaction (Qubex zeta = 2 * xi)",
        ),
        "qubit_qubit_coupling_strength": OutputParameterSpec(
            qid_role="coupling",
            unit="MHz",
            description="Coupling strength estimated from JAZZ and QDash qubit frequencies and anharmonicities",
        ),
    }

    @staticmethod
    def _calculate_coupling_strength(
        *,
        xi: float,
        control_frequency: float,
        target_frequency: float,
        control_qubit_anharmonicity: float,
        target_qubit_anharmonicity: float,
    ) -> float:
        """Return the dispersive coupling estimate in GHz using the Qubex formula."""
        detuning = control_frequency - target_frequency
        denominator = control_qubit_anharmonicity + target_qubit_anharmonicity
        if math.isclose(denominator, 0.0, abs_tol=1e-15):
            raise ValueError("The sum of the two anharmonicities must be non-zero")
        return math.sqrt(
            abs(
                xi
                * (detuning + control_qubit_anharmonicity)
                * (detuning - target_qubit_anharmonicity)
                / denominator
            )
        )

    def _optional_anharmonicities(self) -> tuple[float, float] | None:
        """Return both resolved DB anharmonicities, or ``None`` when either is absent."""
        control = self.input_parameters["control_qubit_anharmonicity"].value
        target = self.input_parameters["target_qubit_anharmonicity"].value
        if control is None or target is None:
            return None
        return float(control), float(target)

    def _run_kwargs(self) -> dict[str, Any]:
        """Return validated options passed to Qubex JAZZ."""
        time_range = np.asarray(self.run_parameters["time_range"].get_value(), dtype=float)
        if time_range.ndim != 1 or time_range.size == 0:
            raise ValueError("time_range must be a non-empty 1D array")
        if not np.isfinite(time_range).all() or np.any(time_range < 0):
            raise ValueError("time_range must contain finite nonnegative values")
        if time_range.size > 1 and np.any(np.diff(time_range) <= 0):
            raise ValueError("time_range must be strictly increasing")

        shots = int(self.run_parameters["shots"].get_value())
        interval = float(self.run_parameters["interval"].get_value())
        if shots <= 0:
            raise ValueError("shots must be positive")
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("interval must be finite and positive")
        return {
            "time_range": time_range,
            "n_shots": shots,
            "shot_interval": interval,
            "plot": False,
        }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        data = run_result.raw_result.data
        zeta = data.get("zeta")
        zeta_error = finite_value_error(zeta, "static_zz_interaction")
        self.output_parameters["static_zz_interaction"].value = (
            zeta * 1e6 if zeta is not None else None
        )  # GHz to KHz

        strength = None
        anharmonicities = self._optional_anharmonicities()
        if zeta_error is None and anharmonicities is not None:
            control_qubit_anharmonicity, target_qubit_anharmonicity = anharmonicities
            strength = self._calculate_coupling_strength(
                xi=float(zeta) / 2,
                control_frequency=self._get_calibration_value("control_qubit_frequency"),
                target_frequency=self._get_calibration_value("target_qubit_frequency"),
                control_qubit_anharmonicity=control_qubit_anharmonicity,
                target_qubit_anharmonicity=target_qubit_anharmonicity,
            )
        self.output_parameters["qubit_qubit_coupling_strength"].value = (
            strength * 1e3 if strength is not None else None
        )

        figure = data.get("fig")
        output_parameters = dict(self.attach_execution_id(execution_id))
        if strength is None:
            output_parameters.pop("qubit_qubit_coupling_strength")
        return PostProcessResult(
            output_parameters=output_parameters,
            figures=[figure] if figure is not None else [],
            validation_error=first_validation_error(
                zeta_error,
                (
                    finite_value_error(
                        strength,
                        "qubit_qubit_coupling_strength",
                        minimum=0.0,
                    )
                    if strength is not None
                    else None
                ),
            ),
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        control_qid, target_qid = qid.split("-", maxsplit=1)
        measured = self.get_qubit_label(backend, control_qid)
        spectator = self.get_qubit_label(backend, target_qid)
        measured_resonator = self.get_resonator_label(backend, control_qid)
        spectator_resonator = self.get_resonator_label(backend, target_qid)

        control_frequency = self._get_calibration_value("control_qubit_frequency")
        target_frequency = self._get_calibration_value("target_qubit_frequency")
        exp.params.readout_amplitude[measured] = self._get_calibration_value(
            "control_readout_amplitude"
        )
        exp.params.readout_amplitude[spectator] = self._get_calibration_value(
            "target_readout_amplitude"
        )

        with exp.modified_frequencies(
            {
                measured: control_frequency,
                spectator: target_frequency,
                measured_resonator: self._get_calibration_value("control_readout_frequency"),
                spectator_resonator: self._get_calibration_value("target_readout_frequency"),
            }
        ):
            result = exp.jazz_experiment(
                target_qubit=measured,
                spectator_qubit=spectator,
                x90={measured: exp.hpi_pulse[measured]},
                x180={
                    measured: exp.hpi_pulse[measured].repeated(2),
                    spectator: exp.hpi_pulse[spectator].repeated(2),
                },
                **self._run_kwargs(),
            )

        return RunResult(raw_result=result, r2={qid: result.data.get("r2")})
