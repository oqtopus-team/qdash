"""Service that re-runs spectroscopy analysis on previously stored task results.

This is the preview-only first slice: load the original Plotly figure that
the workflow saved, re-run the resonator/qubit frequency estimator with new
parameters, and return the marked figure plus output values. The DB is not
mutated.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bunnet import SortDirection
from fastapi import HTTPException
from qdash.analysis.spectroscopy import (
    NUM_RESONATORS,
    PEAK_POSITIONS,
    EstimateQubitFrequencyConfig,
    EstimateResonatorFrequencyConfig,
    create_bare_shift_boundary_estimator,
    create_marked_figure,
    estimate_and_mark_qubit_figure,
    estimate_resonator_frequency_from_figure,
)
from qdash.api.schemas.reanalysis import (
    ReanalyzeOutputParameter,
    ReanalyzeQubitSpectroscopyParams,
    ReanalyzeResonatorSpectroscopyParams,
    ReanalyzeResponse,
)
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    import plotly.graph_objs as go

logger = logging.getLogger(__name__)


RESONATOR_TASK_NAME = "CheckResonatorSpectroscopy"
QUBIT_TASK_NAME = "CheckQubitSpectroscopy"


class ReanalysisService:
    """Re-execute spectroscopy analyses against stored task results (preview only)."""

    def reanalyze_resonator_spectroscopy(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
        params: ReanalyzeResonatorSpectroscopyParams,
        source_task_id: str | None = None,
    ) -> ReanalyzeResponse:
        """Re-run resonator-spectroscopy analysis with the given overrides."""
        doc = self._load_source_doc(
            project_id=project_id,
            chip_id=chip_id,
            qid=qid,
            task_name=RESONATOR_TASK_NAME,
            source_task_id=source_task_id,
        )
        raw_fig = self._load_raw_figure(doc)

        config = self._build_resonator_config(params, doc.run_parameters)

        # Resolve bare-shift estimator: form override → original task's run_parameters
        # → "config". This way, leaving the form blank reproduces the original run.
        estimator_type = params.bare_shift_estimator_type or self._stored_value(
            doc.run_parameters, "bare_shift_estimator_type", default="config"
        )
        if estimator_type and estimator_type != "config":
            strength_limit = params.bare_shift_strength_limit
            if strength_limit is None:
                stored_limit = self._stored_value(
                    doc.run_parameters, "bare_shift_strength_limit", default=4.0
                )
                strength_limit = float(stored_limit) if stored_limit is not None else 4.0
            estimator = create_bare_shift_boundary_estimator(
                type=estimator_type,
                args={"strength_limit": strength_limit},
            )
            trace = raw_fig.data[0]
            boundary = estimator.estimate_bare_shift_boundary(
                list(trace.x), list(trace.y), list(trace.z)
            )
            config = config.with_boundary(boundary)

        resonances, rejected, frequencies = estimate_resonator_frequency_from_figure(
            raw_fig, config
        )
        marked_fig = create_marked_figure(raw_fig, resonances, rejected_resonances=rejected)

        readout_frequency = self._pick_resonator_for_qid(qid, frequencies)
        outputs = [
            ReanalyzeOutputParameter(
                name="readout_frequency",
                value=readout_frequency,
                unit="GHz",
            )
        ]
        return ReanalyzeResponse(
            source_task_id=doc.task_id,
            source_task_name=doc.name,
            qid=qid,
            figure=self._figure_to_dict(marked_fig),
            output_parameters=outputs,
        )

    def reanalyze_qubit_spectroscopy(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
        params: ReanalyzeQubitSpectroscopyParams,
        source_task_id: str | None = None,
    ) -> ReanalyzeResponse:
        """Re-run qubit-spectroscopy analysis with the given overrides."""
        doc = self._load_source_doc(
            project_id=project_id,
            chip_id=chip_id,
            qid=qid,
            task_name=QUBIT_TASK_NAME,
            source_task_id=source_task_id,
        )
        raw_fig = self._load_raw_figure(doc)

        config = self._build_qubit_config(params, doc.run_parameters)
        retry_with_trim = bool(params.retry_with_trim)

        marked_fig, freq_result = estimate_and_mark_qubit_figure(
            raw_fig, config, retry_with_trim=retry_with_trim
        )

        outputs: list[ReanalyzeOutputParameter] = []
        if freq_result.f01 is not None:
            outputs.append(
                ReanalyzeOutputParameter(
                    name="qubit_frequency",
                    value=float(freq_result.f01.frequency),
                    unit="GHz",
                )
            )
            outputs.append(
                ReanalyzeOutputParameter(
                    name="f01_repr_db",
                    value=float(freq_result.f01.repr_db),
                    unit="dB",
                )
            )
            outputs.append(
                ReanalyzeOutputParameter(
                    name="f01_quality_level",
                    value=float(freq_result.f01.quality_level),
                    unit="a.u.",
                )
            )
        if freq_result.anharmonicity is not None:
            outputs.append(
                ReanalyzeOutputParameter(
                    name="anharmonicity",
                    value=float(freq_result.anharmonicity),
                    unit="GHz",
                )
            )

        return ReanalyzeResponse(
            source_task_id=doc.task_id,
            source_task_name=doc.name,
            qid=qid,
            figure=self._figure_to_dict(marked_fig),
            output_parameters=outputs,
        )

    # ── Internal helpers ────────────────────────────────────────────────────

    def _load_source_doc(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
        task_name: str,
        source_task_id: str | None,
    ) -> TaskResultHistoryDocument:
        """Resolve the TaskResultHistoryDocument to re-analyze."""
        if source_task_id:
            doc = TaskResultHistoryDocument.find_one(
                {"project_id": project_id, "task_id": source_task_id}
            ).run()
            if doc is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Task result {source_task_id!r} not found in project {project_id!r}.",
                )
            if doc.chip_id != chip_id or doc.qid != qid or doc.name != task_name:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Task result {source_task_id!r} does not match "
                        f"(chip_id={chip_id}, qid={qid}, name={task_name})."
                    ),
                )
            return doc

        doc = TaskResultHistoryDocument.find_one(
            {
                "project_id": project_id,
                "chip_id": chip_id,
                "name": task_name,
                "qid": qid,
            },
            sort=[("end_at", SortDirection.DESCENDING)],
        ).run()
        if doc is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No {task_name} result found for chip_id={chip_id}, qid={qid} "
                    f"in project {project_id}."
                ),
            )
        return doc

    @staticmethod
    def _load_raw_figure(doc: TaskResultHistoryDocument) -> go.Figure:
        """Load the raw Plotly figure (index 0) from the task result document."""
        import plotly.io as pio

        if not doc.json_figure_path:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Task result {doc.task_id!r} has no stored figure JSON; " "cannot re-analyze."
                ),
            )
        figure_path = Path(doc.json_figure_path[0])
        if not figure_path.exists():
            raise HTTPException(
                status_code=410,
                detail=f"Figure file {figure_path} for task {doc.task_id!r} is missing on disk.",
            )
        try:
            return pio.from_json(figure_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse figure JSON for task {doc.task_id!r}: {exc}",
            ) from exc

    @staticmethod
    def _figure_to_dict(fig: go.Figure) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(fig.to_json())
        return result

    @staticmethod
    def _stored_value(stored_run_parameters: dict[str, Any], name: str, default: Any = None) -> Any:
        """Pull a single value out of a TaskResultHistoryDocument.run_parameters dict.

        ``run_parameters`` is stored as ``{name: {"value": ..., "value_type": ...}}``.
        """
        stored = stored_run_parameters.get(name)
        if isinstance(stored, dict) and "value" in stored:
            return stored["value"]
        return default

    @staticmethod
    def _build_resonator_config(
        params: ReanalyzeResonatorSpectroscopyParams,
        stored_run_parameters: dict[str, Any],
    ) -> EstimateResonatorFrequencyConfig:
        """Build a config; missing fields fall back to the stored task's run_parameters."""
        defaults = EstimateResonatorFrequencyConfig()

        def pick(name: str, fallback: Any) -> Any:
            value = getattr(params, name, None)
            if value is not None:
                return value
            stored = stored_run_parameters.get(name)
            if isinstance(stored, dict) and "value" in stored:
                return stored["value"]
            return fallback

        return EstimateResonatorFrequencyConfig(
            num_resonators=int(pick("num_resonators", defaults.num_resonators)),
            high_power_min=pick("high_power_min", defaults.high_power_min),
            high_power_max=pick("high_power_max", defaults.high_power_max),
            low_power=pick("low_power", defaults.low_power),
            find_peaks_conf_high=defaults.find_peaks_conf_high,
            find_peaks_conf_low=defaults.find_peaks_conf_low,
            group_peaks_conf=defaults.group_peaks_conf,
            compose_resonances_conf=defaults.compose_resonances_conf,
            group_resonances_conf=defaults.group_resonances_conf,
        )

    @staticmethod
    def _build_qubit_config(
        params: ReanalyzeQubitSpectroscopyParams,
        stored_run_parameters: dict[str, Any],
    ) -> EstimateQubitFrequencyConfig:
        defaults = EstimateQubitFrequencyConfig()

        def pick(name: str, fallback: Any) -> Any:
            value = getattr(params, name, None)
            if value is not None:
                return value
            stored = stored_run_parameters.get(name)
            if isinstance(stored, dict) and "value" in stored:
                return stored["value"]
            return fallback

        return EstimateQubitFrequencyConfig(
            binarize_threshold_sigma_plus=float(
                pick("binarize_threshold_sigma_plus", defaults.binarize_threshold_sigma_plus)
            ),
            binarize_threshold_sigma_minus=float(
                pick("binarize_threshold_sigma_minus", defaults.binarize_threshold_sigma_minus)
            ),
            top_power=float(pick("top_power", defaults.top_power)),
            f01_height_min=float(pick("f01_height_min", defaults.f01_height_min)),
            f01_moment_thresholds=defaults.f01_moment_thresholds,
            f12_distance_min=float(pick("f12_distance_min", defaults.f12_distance_min)),
            f12_distance_max=float(pick("f12_distance_max", defaults.f12_distance_max)),
            f12_height_min=float(pick("f12_height_min", defaults.f12_height_min)),
        )

    @staticmethod
    def _pick_resonator_for_qid(qid: str, frequencies: list[float]) -> float:
        """Map the requested qid to one of the four resonator frequencies in the MUX.

        Mirrors the logic in CheckResonatorSpectroscopy.postprocess so the
        re-analysis preview matches what the workflow would have stored.
        """
        if not frequencies:
            return 0.0
        if len(frequencies) != NUM_RESONATORS:
            logger.warning(
                "Resonator reanalysis for qid=%s produced %d frequencies (expected %d); "
                "using order-preserved fallback.",
                qid,
                len(frequencies),
                NUM_RESONATORS,
            )
            try:
                return float(frequencies[int(qid) % len(frequencies)])
            except ValueError:
                return float(frequencies[0])
        try:
            id_in_mux = int(qid) % 4
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"qid {qid!r} is not a valid integer qubit id."
            ) from exc
        return float(frequencies[PEAK_POSITIONS[id_in_mux]])
