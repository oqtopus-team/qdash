"""Service that re-runs spectroscopy analysis on previously stored task results.

This is the preview-only first slice: load the original Plotly figure that
the workflow saved, re-run the resonator/qubit frequency estimator with new
parameters, and return the marked figure plus output values. The DB is not
mutated.
"""

from __future__ import annotations

import json
import logging
import math
from typing import TYPE_CHECKING, Any

from bunnet import SortDirection
from fastapi import HTTPException

from qdash.analysis.spectroscopy import (
    NUM_RESONATORS,
    EstimateQubitFrequencyConfig,
    EstimateResonatorFrequencyConfig,
    create_bare_shift_boundary_estimator,
    create_marked_figure,
    estimate_and_mark_qubit_figure,
    estimate_local_bare_shift_boundary,
    estimate_minimum_usable_power,
    estimate_optimal_powers,
    estimate_resonator_frequency_from_figure,
    guess_sorted_slots_for_partial_mux,
    peak_positions_from_assignment_order,
    qid_for_sorted_slot,
    resolve_resonator_assignment_order,
)
from qdash.api.schemas.reanalysis import (
    ReanalyzeAffectedQubit,
    ReanalyzeOutputParameter,
    ReanalyzeQubitSpectroscopyParams,
    ReanalyzeResonatorSpectroscopyParams,
    ReanalyzeResponse,
)
from qdash.api.services.qubit_parameter_service import QubitParameterService
from qdash.common.config.path_resolver import resolve_calib_data_path
from qdash.common.visualization.figure_metadata import FIGURE_ROLE_META_KEY
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument
from qdash.repository.qubit import MongoQubitCalibrationRepository

if TYPE_CHECKING:
    import plotly.graph_objs as go

logger = logging.getLogger(__name__)


RESONATOR_TASK_NAME = "CheckResonatorSpectroscopy"
QUBIT_TASK_NAME = "CheckQubitSpectroscopy"


class ReanalysisService:
    """Re-execute spectroscopy analyses against stored task results."""

    def __init__(
        self,
        qubit_repo: MongoQubitCalibrationRepository | None = None,
        parameter_service: QubitParameterService | None = None,
    ) -> None:
        self._qubit_repo = qubit_repo or MongoQubitCalibrationRepository()
        # Commit and provenance are shared with the manual per-task parameter editor.
        self._parameter_service = parameter_service or QubitParameterService(self._qubit_repo)

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

        resonances, _rejected, frequencies = estimate_resonator_frequency_from_figure(
            raw_fig, config
        )
        marked_fig = create_marked_figure(raw_fig, resonances)

        trace = raw_fig.data[0]
        assignment_order = self._pick_resonator_assignment_order(params, doc.run_parameters)
        optimal_powers = self._estimate_optimal_powers(trace, resonances, config)
        affected_qubits = self._build_resonator_affected_qubits(
            qid,
            list(trace.x),
            frequencies,
            optimal_powers=optimal_powers,
            assignment_order=assignment_order,
            manual_resonator_slot=params.manual_resonator_slot,
            manual_readout_frequency=params.manual_readout_frequency,
            manual_readout_frequencies=params.manual_readout_frequencies,
        )
        self._apply_current_calibration_values(
            affected_qubits,
            project_id=project_id,
            chip_id=chip_id,
        )
        self._apply_snapshot_values(affected_qubits, project_id=project_id, source_doc=doc)
        self._apply_output_parameter_overrides(
            affected_qubits,
            params.output_parameter_overrides,
        )
        self._derive_readout_amplitudes(affected_qubits, params.output_parameter_overrides)
        # Both figures get the manual markers: the UI shows the unmarked one so the manual
        # values stand alone, while the marked one keeps the auto-detected peaks alongside.
        for figure in (marked_fig, raw_fig):
            self._add_manual_readout_markers(
                figure,
                qid=qid,
                assignment_order=assignment_order,
                manual_readout_frequency=params.manual_readout_frequency,
                manual_readout_frequencies=params.manual_readout_frequencies,
                output_parameter_overrides=params.output_parameter_overrides,
            )
            self._add_manual_power_markers(
                figure,
                affected_qubits=affected_qubits,
                output_parameter_overrides=params.output_parameter_overrides,
            )
        outputs = self._outputs_for_qid(affected_qubits, qid)
        return ReanalyzeResponse(
            source_task_id=doc.task_id,
            source_task_name=doc.name,
            qid=qid,
            figure=self._figure_to_dict(marked_fig),
            raw_figure=self._figure_to_dict(raw_fig),
            output_parameters=outputs,
            affected_qubits=affected_qubits,
        )

    def commit_reanalyze_resonator_spectroscopy(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
        params: ReanalyzeResonatorSpectroscopyParams,
        source_task_id: str | None,
        username: str,
    ) -> ReanalyzeResponse:
        """Persist a resonator-spectroscopy reanalysis preview to all affected MUX qubits."""
        response = self.reanalyze_resonator_spectroscopy(
            project_id=project_id,
            chip_id=chip_id,
            qid=qid,
            params=params,
            source_task_id=source_task_id,
        )
        affected_qubits = [
            affected
            for affected in response.affected_qubits
            if self._outputs_are_committable(affected.output_parameters)
        ]
        if not affected_qubits:
            raise HTTPException(
                status_code=409,
                detail="Reanalysis produced no valid MUX qubit outputs to commit.",
            )

        source_doc = self._parameter_service.load_source_task_result(
            project_id=project_id,
            task_id=response.source_task_id,
        )

        self._parameter_service.commit_output_parameters(
            project_id=project_id,
            chip_id=chip_id,
            username=username,
            source_doc=source_doc,
            source_qid=qid,
            outputs_by_qid={
                affected.qid: self._output_parameter_dict(affected.output_parameters)
                for affected in affected_qubits
            },
            kind="reanalysis",
        )

        response.affected_qubits = affected_qubits
        response.committed = True
        return response

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

        snapshot = doc.output_parameters or {}
        for output in outputs:
            output.snapshot_value = self._parameter_numeric_value(snapshot.get(output.name))

        return ReanalyzeResponse(
            source_task_id=doc.task_id,
            source_task_name=doc.name,
            qid=qid,
            figure=self._figure_to_dict(marked_fig),
            raw_figure=self._figure_to_dict(raw_fig),
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
        """Load the raw Plotly figure from the task result document."""
        import plotly.io as pio

        if not doc.json_figure_path:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Task result {doc.task_id!r} has no stored figure JSON; cannot re-analyze."
                ),
            )

        loaded_figures: list[go.Figure] = []
        missing_paths: list[str] = []
        for stored_path in doc.json_figure_path:
            figure_path = resolve_calib_data_path(stored_path)
            if not figure_path.exists():
                missing_paths.append(str(figure_path))
                continue
            try:
                fig = pio.from_json(figure_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to parse figure JSON for task {doc.task_id!r}: {exc}",
                ) from exc
            loaded_figures.append(fig)
            meta = getattr(getattr(fig, "layout", None), "meta", None)
            if isinstance(meta, dict) and meta.get(FIGURE_ROLE_META_KEY) == "raw":
                return fig

        if loaded_figures:
            return loaded_figures[-1]

        raise HTTPException(
            status_code=410,
            detail=(
                f"Figure files for task {doc.task_id!r} are missing on disk: "
                f"{', '.join(missing_paths)}"
            ),
        )

    @staticmethod
    def _add_manual_readout_markers(
        fig: go.Figure,
        *,
        qid: str,
        assignment_order: list[int],
        manual_readout_frequency: float | None = None,
        manual_readout_frequencies: list[float | None] | None = None,
        output_parameter_overrides: dict[str, dict[str, float]] | None = None,
    ) -> None:
        try:
            qid_int = int(qid)
        except ValueError:
            return

        mux_index = qid_int // NUM_RESONATORS
        peak_positions = peak_positions_from_assignment_order(assignment_order)
        manual_values: list[tuple[str, float]] = []
        for sorted_slot, frequency in enumerate(manual_readout_frequencies or []):
            if frequency is None:
                continue
            assigned_qid = str(qid_for_sorted_slot(mux_index, sorted_slot, peak_positions))
            manual_values.append((assigned_qid, float(frequency)))
        if manual_readout_frequency is not None:
            manual_values.append((qid, float(manual_readout_frequency)))
        # Overrides are keyed by qid, so they need no slot assignment to be marked.
        for override_qid, parameter_values in (output_parameter_overrides or {}).items():
            frequency = parameter_values.get("readout_frequency")
            if frequency is None:
                continue
            manual_values.append((override_qid, float(frequency)))

        for marker_qid, frequency in manual_values:
            fig.add_vline(
                x=frequency,
                line_width=2,
                line_color="white",
                line_dash="dot",
                annotation_text=f"manual Q{marker_qid}",
                annotation_position="top right",
            )

    @staticmethod
    def _add_manual_power_markers(
        fig: go.Figure,
        *,
        affected_qubits: list[ReanalyzeAffectedQubit],
        output_parameter_overrides: dict[str, dict[str, float]] | None = None,
    ) -> None:
        """Star the (frequency, power) point behind a manually picked optimal_power.

        A power is a y value, so a vertical line cannot show it. The star sits at the readout
        frequency of the same qubit, which is where the value was read off the map.
        """
        if not output_parameter_overrides:
            return

        for affected in affected_qubits:
            qid_overrides = output_parameter_overrides.get(affected.qid)
            if not qid_overrides or "optimal_power" not in qid_overrides:
                continue
            power = float(qid_overrides["optimal_power"])
            frequency = next(
                (
                    parameter.value
                    for parameter in affected.output_parameters
                    if parameter.name == "readout_frequency"
                ),
                None,
            )
            if frequency is None or not math.isfinite(frequency) or not math.isfinite(power):
                continue
            fig.add_scatter(
                x=[frequency],
                y=[power],
                mode="markers+text",
                marker={
                    "symbol": "star",
                    "size": 14,
                    "color": "white",
                    "line": {"color": "black", "width": 1},
                },
                text=[f"manual Q{affected.qid}"],
                textposition="bottom center",
                textfont={"color": "white"},
                name=f"manual Q{affected.qid} power",
                showlegend=False,
                hoverinfo="skip",
            )

    @staticmethod
    def _figure_to_dict(fig: go.Figure) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(fig.to_json())
        return result

    @staticmethod
    def _output_parameter_dict(
        output_parameters: list[ReanalyzeOutputParameter],
    ) -> dict[str, dict[str, Any]]:
        return {
            output.name: {
                "value": output.value,
                "unit": output.unit,
                "description": f"Reanalyzed {output.name}",
            }
            for output in output_parameters
        }

    def _apply_current_calibration_values(
        self,
        affected_qubits: list[ReanalyzeAffectedQubit],
        *,
        project_id: str,
        chip_id: str,
    ) -> None:
        for affected in affected_qubits:
            calibration_data = self._qubit_repo.get_calibration_data(
                project_id=project_id,
                chip_id=chip_id,
                qid=affected.qid,
            )
            for output in affected.output_parameters:
                current_value = self._parameter_numeric_value(calibration_data.get(output.name))
                if current_value is not None:
                    output.current_value = current_value

    @classmethod
    def _apply_snapshot_values(
        cls,
        affected_qubits: list[ReanalyzeAffectedQubit],
        *,
        project_id: str,
        source_doc: TaskResultHistoryDocument,
    ) -> None:
        """Fill in the snapshot each qubit's own task result stored when the experiment ran.

        Every MUX qubit has its own task result from the same execution, which is where the
        other qubits' snapshots live.
        """
        qids = [affected.qid for affected in affected_qubits]
        snapshot_by_qid: dict[str, dict[str, Any]] = {}

        sibling_docs = TaskResultHistoryDocument.find(
            {
                "project_id": project_id,
                "execution_id": source_doc.execution_id,
                "name": source_doc.name,
                "qid": {"$in": qids},
            }
        ).run()
        for doc in sibling_docs:
            snapshot_by_qid[doc.qid] = doc.output_parameters or {}
        snapshot_by_qid.setdefault(source_doc.qid, source_doc.output_parameters or {})

        for affected in affected_qubits:
            snapshot = snapshot_by_qid.get(affected.qid, {})
            for output in affected.output_parameters:
                output.snapshot_value = cls._parameter_numeric_value(snapshot.get(output.name))

    @staticmethod
    def _parameter_numeric_value(raw_parameter: Any) -> float | None:
        if isinstance(raw_parameter, dict):
            value = raw_parameter.get("value")
        else:
            value = raw_parameter
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        numeric_value = float(value)
        return numeric_value if math.isfinite(numeric_value) else None

    @staticmethod
    def _apply_output_parameter_overrides(
        affected_qubits: list[ReanalyzeAffectedQubit],
        overrides: dict[str, dict[str, float]] | None,
    ) -> None:
        if not overrides:
            return

        affected_by_qid = {affected.qid: affected for affected in affected_qubits}
        for qid, parameter_values in overrides.items():
            affected = affected_by_qid.get(qid)
            if affected is None:
                affected = ReanalyzeAffectedQubit(qid=qid, output_parameters=[])
                affected_qubits.append(affected)
                affected_by_qid[qid] = affected

            parameters_by_name = {
                parameter.name: parameter for parameter in affected.output_parameters
            }
            for name, value in parameter_values.items():
                parameter = parameters_by_name.get(name)
                if parameter is None:
                    affected.output_parameters.append(
                        ReanalyzeOutputParameter(name=name, value=float(value))
                    )
                    parameters_by_name[name] = affected.output_parameters[-1]
                else:
                    parameter.value = float(value)

    @staticmethod
    def _estimate_optimal_powers(
        trace: Any,
        resonances: list[Any],
        config: EstimateResonatorFrequencyConfig,
    ) -> list[float]:
        """Estimate the optimal readout power per detected resonance.

        Mirrors CheckResonatorSpectroscopy. Returns an empty list when the estimate fails,
        which simply leaves optimal_power/readout_amplitude out of the preview.
        """
        try:
            ys = list(trace.y)
            zs = list(trace.z)
            minimum_usable_power = estimate_minimum_usable_power(
                ys,
                zs,
                config.low_power,
                correlation_coefficient_min=(
                    config.minimum_usable_power_correlation_coefficient_min
                ),
            )
            local_boundaries = [
                estimate_local_bare_shift_boundary(ys, resonance) for resonance in resonances
            ]
            return estimate_optimal_powers(ys, local_boundaries, minimum_usable_power)
        except Exception:
            logger.warning("Failed to estimate optimal powers during reanalysis", exc_info=True)
            return []

    @staticmethod
    def _readout_amplitude_for_power(optimal_power: float) -> float:
        """Convert an optimal readout power (dB) to amplitude, as the workflow task does."""
        return float(10 ** (optimal_power / 20))

    @classmethod
    def _derive_readout_amplitudes(
        cls,
        affected_qubits: list[ReanalyzeAffectedQubit],
        overrides: dict[str, dict[str, float]] | None,
    ) -> None:
        """Keep readout_amplitude consistent with a manually overridden optimal_power."""
        if not overrides:
            return

        for affected in affected_qubits:
            qid_overrides = overrides.get(affected.qid)
            if not qid_overrides or "optimal_power" not in qid_overrides:
                continue
            if "readout_amplitude" in qid_overrides:
                continue
            amplitude = cls._readout_amplitude_for_power(float(qid_overrides["optimal_power"]))
            for parameter in affected.output_parameters:
                if parameter.name == "readout_amplitude":
                    parameter.value = amplitude
                    break

    @staticmethod
    def _outputs_are_committable(output_parameters: list[ReanalyzeOutputParameter]) -> bool:
        return bool(output_parameters) and all(
            math.isfinite(output.value) for output in output_parameters
        )

    @staticmethod
    def _outputs_for_qid(
        affected_qubits: list[ReanalyzeAffectedQubit], qid: str
    ) -> list[ReanalyzeOutputParameter]:
        for affected in affected_qubits:
            if affected.qid == qid:
                return affected.output_parameters
        return [ReanalyzeOutputParameter(name="readout_frequency", value=0.0, unit="GHz")]

    @staticmethod
    def _build_resonator_affected_qubits(
        qid: str,
        xs: list[float],
        frequencies: list[float],
        *,
        optimal_powers: list[float] | None = None,
        assignment_order: list[int],
        manual_resonator_slot: int | None = None,
        manual_readout_frequency: float | None = None,
        manual_readout_frequencies: list[float | None] | None = None,
    ) -> list[ReanalyzeAffectedQubit]:
        try:
            qid_int = int(qid)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"qid {qid!r} is not a valid integer qubit id."
            ) from exc

        peak_positions = peak_positions_from_assignment_order(assignment_order)
        mux_index = qid_int // NUM_RESONATORS
        sorted_slots, _assignment_mode = guess_sorted_slots_for_partial_mux(xs, frequencies)
        values_by_qid: dict[str, float] = {}
        # optimal_power shares the resonance index with the frequency it was estimated for.
        powers_by_qid: dict[str, float] = {}
        for detected_index, (detected_slot, detected_frequency) in enumerate(
            zip(sorted_slots, frequencies, strict=False)
        ):
            if detected_slot is None:
                continue
            assigned_qid = str(qid_for_sorted_slot(mux_index, detected_slot, peak_positions))
            values_by_qid[assigned_qid] = float(detected_frequency)
            if optimal_powers is not None and detected_index < len(optimal_powers):
                powers_by_qid[assigned_qid] = float(optimal_powers[detected_index])

        if manual_resonator_slot is not None and manual_readout_frequency is None:
            try:
                resonance_index = sorted_slots.index(manual_resonator_slot)
            except ValueError:
                resonance_index = None
            if resonance_index is not None and resonance_index < len(frequencies):
                values_by_qid[qid] = float(frequencies[resonance_index])
        if manual_readout_frequencies is not None:
            for sorted_slot, frequency in enumerate(manual_readout_frequencies):
                if frequency is None:
                    continue
                assigned_qid = str(qid_for_sorted_slot(mux_index, sorted_slot, peak_positions))
                values_by_qid[assigned_qid] = float(frequency)
        if manual_readout_frequency is not None:
            values_by_qid[qid] = float(manual_readout_frequency)

        def sort_key(item: tuple[str, float]) -> int:
            try:
                return int(item[0])
            except ValueError:
                return 0

        def outputs_for(affected_qid: str, frequency: float) -> list[ReanalyzeOutputParameter]:
            outputs = [
                ReanalyzeOutputParameter(
                    name="readout_frequency",
                    value=frequency,
                    unit="GHz",
                )
            ]
            power = powers_by_qid.get(affected_qid)
            if power is not None:
                outputs.append(
                    ReanalyzeOutputParameter(name="optimal_power", value=power, unit="dB")
                )
                outputs.append(
                    ReanalyzeOutputParameter(
                        name="readout_amplitude",
                        value=ReanalysisService._readout_amplitude_for_power(power),
                        unit="a.u.",
                        derived_from="optimal_power",
                    )
                )
            return outputs

        return [
            ReanalyzeAffectedQubit(
                qid=affected_qid,
                output_parameters=outputs_for(affected_qid, value),
            )
            for affected_qid, value in sorted(values_by_qid.items(), key=sort_key)
        ]

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
    def _pick_resonator_assignment_order(
        params: ReanalyzeResonatorSpectroscopyParams,
        stored_run_parameters: dict[str, Any],
    ) -> list[int]:
        pattern = params.resonator_assignment_pattern
        if pattern is None:
            stored_pattern = stored_run_parameters.get("resonator_assignment_pattern")
            if isinstance(stored_pattern, dict) and "value" in stored_pattern:
                pattern = str(stored_pattern["value"])

        return list(resolve_resonator_assignment_order(pattern))

    @staticmethod
    def _pick_resonator_for_qid(
        qid: str,
        xs: list[float],
        frequencies: list[float],
        *,
        assignment_order: list[int],
        manual_resonator_slot: int | None = None,
    ) -> float:
        """Map the requested qid to the workflow-equivalent resonator frequency."""
        if not frequencies:
            return 0.0
        try:
            qid_int = int(qid)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"qid {qid!r} is not a valid integer qubit id."
            ) from exc

        id_in_mux = qid_int % NUM_RESONATORS
        peak_positions = peak_positions_from_assignment_order(assignment_order)
        assigned_slot = (
            manual_resonator_slot
            if manual_resonator_slot is not None
            else peak_positions[id_in_mux]
        )
        sorted_slots, assignment_mode = guess_sorted_slots_for_partial_mux(xs, frequencies)
        resonance_index = (
            sorted_slots.index(assigned_slot) if assigned_slot in sorted_slots else None
        )
        if resonance_index is not None and resonance_index < len(frequencies):
            return float(frequencies[resonance_index])

        logger.warning(
            "Resonator reanalysis for qid=%s produced %d frequencies (expected %d); "
            "assigned slot %d unavailable in mode %s.",
            qid,
            len(frequencies),
            NUM_RESONATORS,
            assigned_slot,
            assignment_mode,
        )
        return 0.0
