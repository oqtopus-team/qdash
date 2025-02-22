import numpy as np
from qcflow.qubex_protocols.benchmark.randomized_benchmarking import RandomizedBenchmarking
from qcflow.qubex_protocols.benchmark.x90_interleaved_randomized_benchmarking import (
    X90InterleavedRandomizedBenchmarking,
)
from qcflow.qubex_protocols.benchmark.x180_interleaved_randoized_benchmarking import (
    X180InterleavedRandomizedBenchmarking,
)
from qcflow.qubex_protocols.benchmark.zx90_interleaved_randoized_benchmarking import (
    ZX90InterleavedRandomizedBenchmarking,
)
from qcflow.qubex_protocols.box_setup.check_noise import CheckNoise
from qcflow.qubex_protocols.box_setup.check_status import CheckStatus
from qcflow.qubex_protocols.box_setup.configure import Configure
from qcflow.qubex_protocols.box_setup.dump_box import DumpBox
from qcflow.qubex_protocols.box_setup.link_up import LinkUp
from qcflow.qubex_protocols.measurement.readout_classification import ReadoutClassification
from qcflow.qubex_protocols.one_qubit_coarse.check_effective_qubit_frequency import (
    CheckEffectiveQubitFrequency,
)
from qcflow.qubex_protocols.one_qubit_coarse.check_hpi_pulse import CheckHPIPulse
from qcflow.qubex_protocols.one_qubit_coarse.check_pi_pulse import CheckPIPulse
from qcflow.qubex_protocols.one_qubit_coarse.check_qubit_frequency import (
    CheckQubitFrequency,
)
from qcflow.qubex_protocols.one_qubit_coarse.check_rabi import CheckRabi
from qcflow.qubex_protocols.one_qubit_coarse.check_readout_frequency import (
    CheckReadoutFrequency,
)
from qcflow.qubex_protocols.one_qubit_coarse.check_t1 import CheckT1
from qcflow.qubex_protocols.one_qubit_coarse.check_t2_echo import CheckT2Echo
from qcflow.qubex_protocols.one_qubit_coarse.chevron_pattern import ChevronPattern
from qcflow.qubex_protocols.one_qubit_coarse.create_hpi_pulse import CreateHPIPulse
from qcflow.qubex_protocols.one_qubit_coarse.create_pi_pulse import CreatePIPulse
from qcflow.qubex_protocols.one_qubit_coarse.rabi_oscillation import RabiOscillation
from qcflow.qubex_protocols.one_qubit_fine.check_drag_hpi_pulse import CheckDRAGHPIPulse
from qcflow.qubex_protocols.one_qubit_fine.check_drag_pi_pulse import CheckDRAGPIPulse
from qcflow.qubex_protocols.one_qubit_fine.create_drag_hpi_pulse import CreateDRAGHPIPulse
from qcflow.qubex_protocols.one_qubit_fine.create_drag_pi_pulse import CreateDRAGPIPulse
from qcflow.qubex_protocols.two_qubit.check_cross_resonance import CheckCrossResonance
from qcflow.qubex_protocols.two_qubit.create_fine_zx90 import CreateFineZX90
from qcflow.qubex_protocols.two_qubit.create_zx90 import CreateZX90
from qcflow.qubex_protocols.two_qubit.optimize_zx90 import OptimizeZX90
from qubex.experiment.experiment_constants import (
    CALIBRATION_SHOTS,
    HPI_DURATION,
    PI_DURATION,
    RABI_TIME_RANGE,
)
from qubex.measurement.measurement import DEFAULT_INTERVAL, DEFAULT_SHOTS

task_classes = {
    "CheckStatus": CheckStatus(),
    "LinkUp": LinkUp(),
    "Configure": Configure(),
    "DumpBox": DumpBox(),
    "CheckNoise": CheckNoise(),
    "RabiOscillation": RabiOscillation(),
    "ChevronPattern": ChevronPattern(),
    "CheckQubitFrequency": CheckQubitFrequency(
        detuning_range=np.linspace(-0.01, 0.01, 21),
        time_range=range(0, 101, 4),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckReadoutFrequency": CheckReadoutFrequency(
        detuning_range=np.linspace(-0.01, 0.01, 21),
        time_range=range(0, 101, 4),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckRabi": CheckRabi(
        time_range=RABI_TIME_RANGE,
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CreateHPIPulse": CreateHPIPulse(
        hpi_length=HPI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckHPIPulse": CheckHPIPulse(),
    "CreatePIPulse": CreatePIPulse(
        pi_length=PI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckPIPulse": CheckPIPulse(),
    "CheckT1": CheckT1(
        time_range=np.logspace(
            np.log10(100),
            np.log10(500 * 1000),
            51,
        ),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckT2Echo": CheckT2Echo(
        time_range=np.logspace(
            np.log10(300),
            np.log10(100 * 1000),
            51,
        ),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckEffectiveQubitFrequency": CheckEffectiveQubitFrequency(
        detuning=0.001,
        time_range=np.arange(0, 20001, 100),
        shots=DEFAULT_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CreateDRAGHPIPulse": CreateDRAGHPIPulse(
        hpi_length=HPI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckDRAGHPIPulse": CheckDRAGHPIPulse(),
    "CreateDRAGPIPulse": CreateDRAGPIPulse(
        pi_length=PI_DURATION,
        shots=CALIBRATION_SHOTS,
        interval=DEFAULT_INTERVAL,
    ),
    "CheckDRAGPIPulse": CheckDRAGPIPulse(),
    "ReadoutClassification": ReadoutClassification(),
    "RandomizedBenchmarking": RandomizedBenchmarking(),
    "X90InterleavedRandomizedBenchmarking": X90InterleavedRandomizedBenchmarking(),
    "X180InterleavedRandomizedBenchmarking": X180InterleavedRandomizedBenchmarking(),
    "ZX90InterleavedRandomizedBenchmarking": ZX90InterleavedRandomizedBenchmarking(),
    "CheckCrossResonance": CheckCrossResonance(),
    "CreateFineZX90": CreateFineZX90(),
    "CreateZX90": CreateZX90(),
    "OptimizeZX90": OptimizeZX90(),
}
