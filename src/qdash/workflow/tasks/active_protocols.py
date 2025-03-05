# ruff: noqa
from qdash.neodbmodel.initialize import initialize
from qdash.neodbmodel.task import TaskModel, TaskDocument
from qdash.workflow.tasks.benchmark.randomized_benchmarking import RandomizedBenchmarking
from qdash.workflow.tasks.benchmark.x90_interleaved_randomized_benchmarking import (
    X90InterleavedRandomizedBenchmarking,
)
from qdash.workflow.tasks.benchmark.x180_interleaved_randoized_benchmarking import (
    X180InterleavedRandomizedBenchmarking,
)
from qdash.workflow.tasks.benchmark.zx90_interleaved_randoized_benchmarking import (
    ZX90InterleavedRandomizedBenchmarking,
)
from qdash.workflow.tasks.box_setup.check_noise import CheckNoise
from qdash.workflow.tasks.box_setup.check_status import CheckStatus
from qdash.workflow.tasks.box_setup.configure import Configure
from qdash.workflow.tasks.box_setup.dump_box import DumpBox
from qdash.workflow.tasks.box_setup.link_up import LinkUp
from qdash.workflow.tasks.measurement.readout_classification import ReadoutClassification
from qdash.workflow.tasks.one_qubit_coarse.check_effective_qubit_frequency import (
    CheckEffectiveQubitFrequency,
)
from qdash.workflow.tasks.one_qubit_coarse.check_hpi_pulse import CheckHPIPulse
from qdash.workflow.tasks.one_qubit_coarse.check_pi_pulse import CheckPIPulse
from qdash.workflow.tasks.one_qubit_coarse.check_qubit_frequency import (
    CheckQubitFrequency,
)
from qdash.workflow.tasks.one_qubit_coarse.check_rabi import CheckRabi
from qdash.workflow.tasks.one_qubit_coarse.check_readout_frequency import (
    CheckReadoutFrequency,
)
from qdash.workflow.tasks.one_qubit_coarse.check_t1 import CheckT1
from qdash.workflow.tasks.one_qubit_coarse.check_t2_echo import CheckT2Echo
from qdash.workflow.tasks.one_qubit_coarse.chevron_pattern import ChevronPattern
from qdash.workflow.tasks.one_qubit_coarse.create_hpi_pulse import CreateHPIPulse
from qdash.workflow.tasks.one_qubit_coarse.create_pi_pulse import CreatePIPulse
from qdash.workflow.tasks.one_qubit_coarse.rabi_oscillation import RabiOscillation
from qdash.workflow.tasks.one_qubit_fine.check_drag_hpi_pulse import CheckDRAGHPIPulse
from qdash.workflow.tasks.one_qubit_fine.check_drag_pi_pulse import CheckDRAGPIPulse
from qdash.workflow.tasks.one_qubit_fine.create_drag_hpi_pulse import CreateDRAGHPIPulse
from qdash.workflow.tasks.one_qubit_fine.create_drag_pi_pulse import CreateDRAGPIPulse
from qdash.workflow.tasks.two_qubit.check_cross_resonance import CheckCrossResonance
from qdash.workflow.tasks.two_qubit.create_fine_zx90 import CreateFineZX90
from qdash.workflow.tasks.two_qubit.create_zx90 import CreateZX90
from qdash.workflow.tasks.two_qubit.optimize_zx90 import OptimizeZX90
from qdash.workflow.tasks.base import BaseTask


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
