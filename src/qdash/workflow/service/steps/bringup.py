"""Bring-up calibration steps.

This module defines steps for initial qubit characterization:
- BringUp: Resonator and qubit spectroscopy for frequency estimation

Tasks include:
- MUX-level tasks: Executed once per MUX for representative qubit (qid % 4 == 0)
- Qubit-level tasks: Executed for each qubit individually
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from prefect import get_run_logger

from qdash.workflow.service.results import OneQubitResult
from qdash.workflow.service.steps.base import CalibrationStep
from qdash.workflow.service.tasks import BRINGUP_TASKS, EXPERIMENTAL_SIMULTANEOUS_BRINGUP_TASKS

if TYPE_CHECKING:
    from qdash.workflow.service.calib_service import CalibService
    from qdash.workflow.service.steps.pipeline import StepContext
    from qdash.workflow.service.targets import Target


@dataclass
class BringUp(CalibrationStep):
    """Bring-up calibration step for initial qubit characterization.

    Executes BRINGUP_TASKS:
    - CheckResonatorSpectroscopy (MUX-level): Estimates readout_frequency
    - Configure: Apply readout_frequency to backend
    - CheckQubitSpectroscopy: Estimates coarse_qubit_frequency, anharmonicity, coarse_control_amplitude
    - CheckControlAmplitude: Refines control_amplitude via sqrt-Lorentzian fit
    - Configure: Apply qubit_frequency / control_amplitude to backend
    - CheckChevron: Adaptive chevron with rough/fine search for qubit_frequency
    - CheckRabi: Refines control_amplitude (Rabi-rate-derived)
    - CheckFineChevron (x2): Refines qubit_frequency, ±10 MHz, with the latest control_amplitude
    - CheckRabi (x2): Refines control_amplitude with the latest qubit_frequency
      Two fine/rabi iterations converge to sub-kHz qubit_frequency for typical transmons.

    MUX-level tasks run once per MUX for the representative qubit (qid % 4 == 0).
    Qubit-level tasks run for each qubit individually.

    Provides: bringup

    Metrics extracted:
    - readout_frequency (GHz): From resonator spectroscopy
    - readout_amplitude (a.u.): From resonator spectroscopy optimal power
    - qubit_frequency (GHz): f01 transition frequency from qubit spectroscopy
    - anharmonicity (GHz): alpha = f12 - f01 (typically negative for transmon)

    Example:
        # Basic usage
        BringUp()

        # With custom tasks
        BringUp(tasks=["CheckResonatorSpectroscopy", "CheckQubitSpectroscopy"])
    """

    mode: str = "scheduled"
    tasks: list[str] = field(default_factory=lambda: list(BRINGUP_TASKS))

    @property
    def name(self) -> str:
        return "bringup"

    @property
    def provides(self) -> set[str]:
        return {"bringup"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute MUX-level bring-up calibration.

        Note: MUX tasks are automatically skipped for non-representative qubits
        by the scheduling infrastructure.
        """
        logger = get_run_logger()
        tasks = self.tasks

        logger.info(f"[{self.name}] Starting with mode={self.mode}, {len(tasks)} tasks")

        from qdash.workflow.service.strategy import OneQubitConfig, get_one_qubit_strategy
        from qdash.workflow.service.targets import MuxTargets

        if isinstance(targets, MuxTargets):
            config = OneQubitConfig(
                mux_ids=targets.mux_ids,
                exclude_qids=targets.exclude_qids,
                tasks=tasks,
                flow_name=f"{service.flow_name}_{self.name}" if service.flow_name else self.name,
                project_id=service.project_id,
            )
            strategy = get_one_qubit_strategy(self.mode)
            raw_results = strategy.execute(service, config)
        else:
            qids = targets.to_qids(service.chip_id)
            raw_results = self._execute_direct(service, qids, tasks)

        # Build typed result
        result = self._build_result(raw_results)

        # Store in context metadata
        ctx.metadata["bringup"] = result

        # Count actual executions (exclude skipped)
        executed_count = sum(
            1
            for qid, data in result.qubits.items()
            if data.status == "success" and not data.raw.get("_skipped", False)
        )
        total_muxes = len(targets.mux_ids) if isinstance(targets, MuxTargets) else 0

        logger.info(
            f"[{self.name}] Completed. "
            f"{executed_count} MUX(es) processed"
            + (f" (out of {total_muxes} MUXes)" if total_muxes else "")
        )
        return ctx

    def _execute_direct(
        self,
        service: CalibService,
        qids: list[str],
        tasks: list[str],
    ) -> dict[str, Any]:
        """Direct execution for QubitTargets using multiprocess parallelism."""
        from qdash.workflow.service._internal.scheduling_tasks import (
            run_qubit_calibrations_parallel,
        )

        # Build session config for multiprocess execution
        session_config = {
            "username": service.username,
            "chip_id": service.chip_id,
            "backend_name": service.backend_name,
            "execution_id": service.execution_id,
            "project_id": service.project_id,
            "default_run_parameters": service.default_run_parameters,
            "tags": service.tags,
            "flow_name": service.flow_name,
            "note": service.note,
        }

        results = run_qubit_calibrations_parallel(
            qids=qids,
            tasks=tasks,
            session_config=session_config,
        )
        return {"direct": results}

    def _build_result(self, raw_results: dict[str, Any]) -> OneQubitResult:
        """Build typed result from raw backend data."""
        from qdash.workflow.service.results import QubitCalibData

        result = OneQubitResult()
        for stage_data in raw_results.values():
            if not isinstance(stage_data, dict):
                continue
            for qid, raw in stage_data.items():
                if not isinstance(raw, dict):
                    continue

                # Check if this was a skipped execution (MUX task for non-representative qubit)
                was_skipped = any(
                    isinstance(task_result, dict) and task_result.get("skipped", False)
                    for task_result in raw.values()
                    if isinstance(task_result, dict)
                )

                # Mark skipped qubits as success (intentional skip) with skipped flag in raw
                if was_skipped:
                    raw["_skipped"] = True

                result.add_qubit(
                    qid,
                    QubitCalibData(
                        status="success" if raw.get("status") == "success" else "failed",
                        metrics=self._extract_metrics(raw),
                        raw=raw,
                    ),
                )
        return result

    def _extract_metrics(self, raw: dict[str, Any]) -> dict[str, float]:
        """Extract metrics from raw result."""
        metrics: dict[str, float] = {}

        # Readout parameters from CheckResonatorSpectroscopy
        reso_result = raw.get("CheckResonatorSpectroscopy", {})
        if reso_result and not reso_result.get("skipped", False):
            freq_param = reso_result.get("readout_frequency") or reso_result.get(
                "estimated_resonator_frequency"
            )
            if freq_param is not None:
                metrics["readout_frequency"] = (
                    freq_param.value if hasattr(freq_param, "value") else freq_param
                )
            amp_param = reso_result.get("readout_amplitude")
            if amp_param is not None:
                metrics["readout_amplitude"] = (
                    amp_param.value if hasattr(amp_param, "value") else amp_param
                )

        # Coarse qubit frequency and anharmonicity from CheckQubitSpectroscopy
        qubit_result = raw.get("CheckQubitSpectroscopy", {})
        if qubit_result and not qubit_result.get("skipped", False):
            # Coarse qubit frequency (f01) — proper qubit_frequency comes from
            # CheckChevron's adaptive chevron fit.
            qubit_freq_param = qubit_result.get("coarse_qubit_frequency")
            if qubit_freq_param is not None:
                metrics["coarse_qubit_frequency"] = (
                    qubit_freq_param.value
                    if hasattr(qubit_freq_param, "value")
                    else qubit_freq_param
                )

            # Anharmonicity (α = f12 - f01)
            anharm_param = qubit_result.get("anharmonicity")
            if anharm_param is not None:
                value = anharm_param.value if hasattr(anharm_param, "value") else anharm_param
                if value is not None:
                    metrics["anharmonicity"] = value

        # Proper qubit frequency from CheckChevron. Keep CheckCoarseChevron as
        # a fallback so older persisted results still render metrics.
        chevron_result = raw.get("CheckChevron", {}) or raw.get("CheckCoarseChevron", {})
        if chevron_result and not chevron_result.get("skipped", False):
            qubit_freq_param = chevron_result.get("qubit_frequency")
            if qubit_freq_param is not None:
                metrics["qubit_frequency"] = (
                    qubit_freq_param.value
                    if hasattr(qubit_freq_param, "value")
                    else qubit_freq_param
                )

        return metrics


@dataclass
class ExperimentalSimultaneousBringUp(CalibrationStep):
    """Experimental bring-up using resonator spectroscopy and simultaneous qubit spectroscopy."""

    resonator_mode: str = "scheduled"
    qubit_mode: str = "simultaneous_spectroscopy"
    simultaneous_spectroscopy_schedule_mode: str = "local_index"
    tasks: list[str] = field(default_factory=lambda: list(EXPERIMENTAL_SIMULTANEOUS_BRINGUP_TASKS))

    @property
    def name(self) -> str:
        return "experimental_simultaneous_bringup"

    @property
    def provides(self) -> set[str]:
        return {"experimental_simultaneous_bringup", "bringup"}

    def execute(
        self,
        service: CalibService,
        targets: Target,
        ctx: StepContext,
    ) -> StepContext:
        """Execute resonator and simultaneous qubit spectroscopy in one execution."""
        logger = get_run_logger()
        from qdash.workflow.engine import OneQubitScheduler
        from qdash.workflow.engine.backend.qubex_paths import get_qubex_paths
        from qdash.workflow.service.calib_service import (
            finish_calibration,
            get_session,
            init_calibration,
        )
        from qdash.workflow.service.github import ConfigFileType, GitHubPushConfig
        from qdash.workflow.service.one_qubit_stage_runner import OneQubitStageRunner
        from qdash.workflow.service.targets import MuxTargets

        if not isinstance(targets, MuxTargets):
            msg = "ExperimentalSimultaneousBringUp currently requires MuxTargets"
            raise ValueError(msg)
        if self.resonator_mode != "scheduled":
            msg = "ExperimentalSimultaneousBringUp currently supports resonator_mode='scheduled'"
            raise ValueError(msg)
        if self.qubit_mode != "simultaneous_spectroscopy":
            msg = (
                "ExperimentalSimultaneousBringUp currently supports "
                "qubit_mode='simultaneous_spectroscopy'"
            )
            raise ValueError(msg)

        wiring_config_path = str(get_qubex_paths().wiring_yaml(service.chip_id))
        scheduler = OneQubitScheduler(
            chip_id=service.chip_id, wiring_config_path=wiring_config_path
        )
        reso_schedule = scheduler.generate_from_mux(
            mux_ids=targets.mux_ids, exclude_qids=targets.exclude_qids
        )
        qubit_schedule = scheduler.generate_simultaneous_spectroscopy_batches_from_mux(
            mux_ids=targets.mux_ids,
            exclude_qids=targets.exclude_qids,
            mode=self.simultaneous_spectroscopy_schedule_mode,
        )
        runner = OneQubitStageRunner(service, project_id=service.project_id)

        all_qids = list(
            dict.fromkeys(
                runner.collect_scheduled_qids(reso_schedule)
                + runner.collect_simultaneous_qids(qubit_schedule)
            )
        )
        if not all_qids:
            result = BringUp(tasks=[])._build_result({})
            ctx.metadata["experimental_simultaneous_bringup"] = result
            ctx.metadata["bringup"] = result
            return ctx

        stage_flow_name = f"{service.flow_name}_{self.name}" if service.flow_name else self.name
        created_execution = service.skip_execution or service.execution_service is None
        if created_execution:
            init_calibration(
                service.username,
                service.chip_id,
                all_qids,
                flow_name=stage_flow_name,
                backend_name=service.backend_name,
                tags=service.tags or ([service.flow_name] if service.flow_name else None),
                project_id=service.project_id,
                use_lock=False,
                enable_github_pull=True,
                github_push_config=GitHubPushConfig(
                    enabled=True,
                    file_types=[ConfigFileType.CALIB_NOTE, ConfigFileType.ALL_PARAMS],
                ),
                note={
                    "type": "experimental-simultaneous-bringup",
                    "resonator_strategy": self.resonator_mode,
                    "qubit_strategy": qubit_schedule.metadata["strategy"],
                    "qubit_schedule_mode": self.simultaneous_spectroscopy_schedule_mode,
                    "total_qubits": len(all_qids),
                    "total_steps": qubit_schedule.total_steps,
                },
            )
            session = get_session()
        else:
            session = service

        assert session.execution_id is not None
        session_config = runner.build_session_config(
            execution_id=session.execution_id,
            flow_name=stage_flow_name,
        )

        logger.info("[%s] Running resonator spectroscopy", self.name)
        reso_results = runner.execute_scheduled_mux_schedule(
            reso_schedule,
            tasks=["CheckResonatorSpectroscopy"],
            session_config=session_config,
        )

        logger.info("[%s] Running simultaneous qubit spectroscopy", self.name)
        qubit_results = runner.execute_simultaneous_spectroscopy_schedule(
            qubit_schedule,
            tasks=["CheckSimultaneousQubitSpectroscopy"],
            session_config=session_config,
        )

        session = get_session() if created_execution else service
        stage_results = {"resonator": reso_results, "qubit": qubit_results}
        session.record_stage_result("experimental_simultaneous_bringup", stage_results)
        if created_execution:
            finish_calibration()

        result = BringUp(tasks=[])._build_result(
            {"combined": self._merge_qid_results(reso_results, qubit_results)}
        )
        ctx.metadata["experimental_simultaneous_bringup"] = result
        ctx.metadata["bringup"] = result
        return ctx

    @staticmethod
    def _flatten_strategy_results(raw_results: dict[str, Any]) -> dict[str, Any]:
        """Flatten strategy results from stage/step keys to qid keys."""
        flattened: dict[str, Any] = {}
        for stage_data in raw_results.values():
            if not isinstance(stage_data, dict):
                continue
            flattened.update({qid: raw for qid, raw in stage_data.items() if isinstance(raw, dict)})
        return flattened

    @classmethod
    def _merge_qid_results(cls, *raw_results: dict[str, Any]) -> dict[str, Any]:
        """Merge multiple strategy result payloads by qid."""
        merged: dict[str, Any] = {}
        for raw_result in raw_results:
            for qid, raw in cls._flatten_strategy_results(raw_result).items():
                qid_result = merged.setdefault(qid, {})
                qid_result.update(raw)
                if raw.get("status") == "failed":
                    qid_result["status"] = "failed"
                elif "status" not in qid_result:
                    qid_result["status"] = raw.get("status", "success")
        return merged
