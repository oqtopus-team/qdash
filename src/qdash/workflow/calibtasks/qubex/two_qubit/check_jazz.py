"""Measure static ZZ interaction with Qubex JAZZ."""

from typing import ClassVar

from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL, DEFAULT_SHOTS

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import (
    QubexTask,
    readout_duration_run_parameter,
    required_rabi_normalization_inputs,
)
from qdash.workflow.calibtasks.qubex.validation import finite_value_error
from qdash.workflow.engine.backend.qubex import QubexBackend


class CheckJAZZ(QubexTask):
    """Measure ZZ for a coupling; the first qid is measured, the second is the spectator."""

    name: str = "CheckJAZZ"
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
            default=DEFAULT_SHOTS,
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
        ),
        "control_hpi_amplitude": InputParameterSpec.required_database(
            parameter_name="hpi_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        "control_hpi_duration": InputParameterSpec.required_database(
            parameter_name="hpi_duration",
            qid_role="control",
            unit="ns",
        ),
        "control_readout_frequency": InputParameterSpec.required_database(
            parameter_name="readout_frequency",
            qid_role="control",
            unit="GHz",
            fallback_parameter_names=("resonator_frequency",),
        ),
        "control_readout_amplitude": InputParameterSpec.required_database(
            parameter_name="readout_amplitude",
            qid_role="control",
            unit="a.u.",
        ),
        **required_rabi_normalization_inputs(prefix="target_", qid_role="target"),
        "target_qubit_frequency": InputParameterSpec.required_database(
            parameter_name="control_frequency",
            qid_role="target",
            unit="GHz",
            fallback_parameter_names=("qubit_frequency",),
        ),
        "target_hpi_amplitude": InputParameterSpec.required_database(
            parameter_name="hpi_amplitude",
            qid_role="target",
            unit="a.u.",
        ),
        "target_hpi_duration": InputParameterSpec.required_database(
            parameter_name="hpi_duration",
            qid_role="target",
            unit="ns",
        ),
        "target_readout_frequency": InputParameterSpec.required_database(
            parameter_name="readout_frequency",
            qid_role="target",
            unit="GHz",
            fallback_parameter_names=("resonator_frequency",),
        ),
        "target_readout_amplitude": InputParameterSpec.required_database(
            parameter_name="readout_amplitude",
            qid_role="target",
            unit="a.u.",
        ),
    }

    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "static_zz_interaction": OutputParameterSpec(
            qid_role="coupling",
            unit="KHz",
            description="Signed static ZZ interaction (Qubex zeta = 2 * xi)",
        ),
    }

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        data = run_result.raw_result.data
        zeta = data.get("zeta")
        self.output_parameters["static_zz_interaction"].value = (
            zeta * 1e6 if zeta is not None else None
        )  # GHz to KHz
        figure = data.get("fig")
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=[figure] if figure is not None else [],
            validation_error=finite_value_error(data.get("zeta"), "static_zz_interaction"),
        )

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        measured, spectator = (exp.get_qubit_label(int(q)) for q in qid.split("-"))
        result = exp.jazz_experiment(
            target_qubit=measured,
            spectator_qubit=spectator,
            time_range=self.run_parameters["time_range"].get_value(),
            x90={measured: exp.hpi_pulse[measured]},
            x180={
                measured: exp.hpi_pulse[measured].repeated(2),
                spectator: exp.hpi_pulse[spectator].repeated(2),
            },
            n_shots=self.run_parameters["shots"].get_value(),
            shot_interval=self.run_parameters["interval"].get_value(),
            plot=False,
        )
        return RunResult(raw_result=result, r2={qid: result.data.get("r2")})
