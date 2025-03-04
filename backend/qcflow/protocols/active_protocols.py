# ruff: noqa
from neodbmodel.initialize import initialize
from neodbmodel.task import TaskModel, TaskDocument
from qcflow.protocols.benchmark.randomized_benchmarking import RandomizedBenchmarking
from qcflow.protocols.benchmark.x90_interleaved_randomized_benchmarking import (
    X90InterleavedRandomizedBenchmarking,
)
from qcflow.protocols.benchmark.x180_interleaved_randoized_benchmarking import (
    X180InterleavedRandomizedBenchmarking,
)
from qcflow.protocols.benchmark.zx90_interleaved_randoized_benchmarking import (
    ZX90InterleavedRandomizedBenchmarking,
)
from qcflow.protocols.box_setup.check_noise import CheckNoise
from qcflow.protocols.box_setup.check_status import CheckStatus
from qcflow.protocols.box_setup.configure import Configure
from qcflow.protocols.box_setup.dump_box import DumpBox
from qcflow.protocols.box_setup.link_up import LinkUp
from qcflow.protocols.measurement.readout_classification import ReadoutClassification
from qcflow.protocols.one_qubit_coarse.check_effective_qubit_frequency import (
    CheckEffectiveQubitFrequency,
)
from qcflow.protocols.one_qubit_coarse.check_hpi_pulse import CheckHPIPulse
from qcflow.protocols.one_qubit_coarse.check_pi_pulse import CheckPIPulse
from qcflow.protocols.one_qubit_coarse.check_qubit_frequency import (
    CheckQubitFrequency,
)
from qcflow.protocols.one_qubit_coarse.check_rabi import CheckRabi
from qcflow.protocols.one_qubit_coarse.check_readout_frequency import (
    CheckReadoutFrequency,
)
from qcflow.protocols.one_qubit_coarse.check_t1 import CheckT1
from qcflow.protocols.one_qubit_coarse.check_t2_echo import CheckT2Echo
from qcflow.protocols.one_qubit_coarse.chevron_pattern import ChevronPattern
from qcflow.protocols.one_qubit_coarse.create_hpi_pulse import CreateHPIPulse
from qcflow.protocols.one_qubit_coarse.create_pi_pulse import CreatePIPulse
from qcflow.protocols.one_qubit_coarse.rabi_oscillation import RabiOscillation
from qcflow.protocols.one_qubit_fine.check_drag_hpi_pulse import CheckDRAGHPIPulse
from qcflow.protocols.one_qubit_fine.check_drag_pi_pulse import CheckDRAGPIPulse
from qcflow.protocols.one_qubit_fine.create_drag_hpi_pulse import CreateDRAGHPIPulse
from qcflow.protocols.one_qubit_fine.create_drag_pi_pulse import CreateDRAGPIPulse
from qcflow.protocols.two_qubit.check_cross_resonance import CheckCrossResonance
from qcflow.protocols.two_qubit.create_fine_zx90 import CreateFineZX90
from qcflow.protocols.two_qubit.create_zx90 import CreateZX90
from qcflow.protocols.two_qubit.optimize_zx90 import OptimizeZX90
from qcflow.protocols.base import BaseTask


def generate_task_instances(task_names: list[str], task_details: dict) -> dict[str, BaseTask]:
    task_instances = {}
    initialize()
    for task_name in task_names:
        # task = TaskDocument.find_one({"username": "admin"}, {"name": task_name}).run()
        task_class = BaseTask.registry.get(task_name)
        if task_class is None:
            raise ValueError(f"タスク '{task_name}' は登録されていません")
        task_instance = task_class(task_details[task_name])
        task_instances[task_name] = task_instance
    return task_instances
