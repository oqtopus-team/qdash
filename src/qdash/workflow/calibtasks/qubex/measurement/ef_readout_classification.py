"""Three-state readout classification for GE/EF calibration."""

from typing import Any, ClassVar

from qubex.experiment.experiment_constants import CALIBRATION_SHOTS
from qubex.measurement.measurement_defaults import DEFAULT_INTERVAL

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.base import PostProcessResult, RunResult
from qdash.workflow.calibtasks.qubex.base import QubexTask, readout_duration_run_parameter
from qdash.workflow.calibtasks.qubex.validation import (
    finite_value_error,
    first_validation_error,
    require_ef_configuration,
)
from qdash.workflow.engine.backend.qubex import QubexBackend


class EFReadoutClassification(QubexTask):
    """Build a three-state classifier for the ground, excited, and second-excited states."""

    name: str = "EFReadoutClassification"
    task_type: str = "qubit"
    input_spec: ClassVar[dict[str, InputParameterSpec]] = {
        "control_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("qubit_frequency",), unit="GHz"
        ),
        "ef_frequency": InputParameterSpec.required_database(unit="GHz"),
        "hpi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "hpi_duration": InputParameterSpec.required_database(unit="ns"),
        "ef_hpi_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "ef_hpi_duration": InputParameterSpec.required_database(unit="ns"),
        "readout_amplitude": InputParameterSpec.required_database(unit="a.u."),
        "readout_frequency": InputParameterSpec.required_database(
            fallback_parameter_names=("resonator_frequency",), unit="GHz"
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "readout_duration": readout_duration_run_parameter(),
        "shots": RunParameterSpec(
            unit="a.u.",
            value_type="int",
            default=CALIBRATION_SHOTS,
            description="Shots per prepared state",
        ),
        "interval": RunParameterSpec(
            unit="ns",
            value_type="float",
            default=DEFAULT_INTERVAL,
            description="Time interval between shots",
        ),
    }
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "average_ef_readout_fidelity": OutputParameterSpec(
            unit="a.u.", description="Average three-state readout fidelity"
        ),
        "ef_readout_fidelity_g": OutputParameterSpec(
            unit="a.u.", description="Readout fidelity for prepared ground state"
        ),
        "ef_readout_fidelity_e": OutputParameterSpec(
            unit="a.u.", description="Readout fidelity for prepared excited state"
        ),
        "ef_readout_fidelity_f": OutputParameterSpec(
            unit="a.u.", description="Readout fidelity for prepared second-excited state"
        ),
    }

    def run(self, backend: QubexBackend, qid: str) -> RunResult:
        exp = self.get_experiment(backend)
        label = self.get_qubit_label(backend, qid)
        require_ef_configuration(exp, label)
        exp.params.readout_amplitude[label] = self._get_calibration_value("readout_amplitude")
        with exp.modified_frequencies(
            {
                exp.ctx.resolve_ge_label(label): self._get_calibration_value("control_frequency"),
                exp.ctx.resolve_ef_label(label): self._get_calibration_value("ef_frequency"),
                exp.ctx.resolve_read_label(label): self._get_calibration_value("readout_frequency"),
            }
        ):
            result = exp.build_classifier(
                targets=label,
                n_states=3,
                save_dir=exp.classifier_dir,
                n_shots=self.run_parameters["shots"].get_value(),
                shot_interval=self.run_parameters["interval"].get_value(),
                readout_duration=self.run_parameters["readout_duration"].get_value(),
                plot=False,
            )
        self.save_calibration(backend)
        return RunResult(raw_result=result)

    def postprocess(
        self, backend: QubexBackend, execution_id: str, run_result: RunResult, qid: str
    ) -> PostProcessResult:
        label = self.get_qubit_label(backend, qid)
        result = run_result.raw_result
        fidelities = result.data["readout_fidelities"][label]
        values = {
            "average_ef_readout_fidelity": result.data["average_readout_fidelity"][label],
            "ef_readout_fidelity_g": fidelities[0],
            "ef_readout_fidelity_e": fidelities[1],
            "ef_readout_fidelity_f": fidelities[2],
        }
        for name, value in values.items():
            self.output_parameters[name].value = float(value)
        figures_by_name: dict[str, Any] = getattr(result, "figures", None) or {}
        figures = [
            figures_by_name[key]
            for key in (f"{label}_prepared_0", f"{label}_prepared_1", f"{label}_prepared_2")
            if key in figures_by_name
        ]
        return PostProcessResult(
            output_parameters=self.attach_execution_id(execution_id),
            figures=figures,
            validation_error=first_validation_error(
                *(
                    finite_value_error(value, name, minimum=0, maximum=1)
                    for name, value in values.items()
                )
            ),
        )
