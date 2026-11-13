"""Refine the stored native pulse amplitude with upstream Qibocal flipping."""

from typing import ClassVar

from qdash.datamodel.task import InputParameterSpec, OutputParameterSpec, RunParameterSpec
from qdash.workflow.calibtasks.qibocal.rabi_amplitude import QibocalRabiAmplitude
from qdash.workflow.engine.backend.qibocal import QibocalRequest


class QibocalFlipping(QibocalRabiAmplitude):
    name: str = "QibocalFlipping"
    task_type: str = "qubit"
    chi2_parameter: ClassVar[str] = "qibocal_flipping_chi2"
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
    output_spec: ClassVar[dict[str, OutputParameterSpec]] = {
        "qibocal_pi_duration": OutputParameterSpec(
            unit="ns", description="Duration paired with the refined RX amplitude"
        ),
        "qibocal_pi_amplitude": OutputParameterSpec(
            unit="a.u.", description="Native RX amplitude refined by official Flipping"
        ),
        "qibocal_flipping_chi2": OutputParameterSpec(
            unit="", description="Reduced chi-squared of the Flipping fit"
        ),
    }
    run_spec: ClassVar[dict[str, RunParameterSpec]] = {
        "nshots": RunParameterSpec(
            unit="a.u.", value_type="int", default=1024, description="Shots per sequence"
        ),
        "relaxation_time": RunParameterSpec(
            unit="ns", value_type="float", default=0.0, description="Wait between shots"
        ),
        "seed": RunParameterSpec(
            unit="", value_type="int", default=1234, description="Emulator random seed"
        ),
        "nflips_max": RunParameterSpec(
            unit="", value_type="int", default=20, description="Exclusive maximum flip pairs"
        ),
        "nflips_step": RunParameterSpec(
            unit="", value_type="int", default=1, description="Step in flip pairs"
        ),
        "delta_amplitude": RunParameterSpec(
            unit="a.u.",
            value_type="float",
            default=0.02,
            description="Amplitude detuning for the fit",
        ),
    }

    def build_request(self, qid: str) -> QibocalRequest:
        import math

        from qdash.common.qibocal_platform import CALIBRATION_FIELDS

        parameters = {name: self._run_value(name) for name in self.run_spec if name != "seed"}
        if (
            parameters["nflips_step"] <= 0
            or parameters["nflips_max"] / parameters["nflips_step"] < 6
        ):
            raise ValueError("Flipping requires at least six points and a positive step")
        if not all(math.isfinite(float(value)) for value in parameters.values()):
            raise ValueError("Flipping parameters must be finite")
        if parameters["nshots"] <= 0 or parameters["relaxation_time"] < 0:
            raise ValueError("Invalid shots or relaxation time")
        return QibocalRequest(
            qubit=int(qid),
            seed=int(self._run_value("seed")),
            protocol="flipping",
            parameters=parameters,
            calibration={
                field.name: field.validate(self.input_parameters[field.name].value)
                for field in CALIBRATION_FIELDS
            },
        )
