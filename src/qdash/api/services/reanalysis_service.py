"""Service that re-runs spectroscopy analysis on previously stored task results.

This is the preview-only first slice: load the original (raw) Plotly figure
that the workflow saved, re-run the resonator/qubit frequency estimator with new
parameters, and return the marked figure plus the same seed outputs the workflow
task would publish. Optionally the marked figure is also rendered to PNG for
image-based evaluation. The DB is not mutated.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import re
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any

from bunnet import SortDirection
from fastapi import HTTPException

from qdash.analysis.spectroscopy import (
    NUM_RESONATORS,
    BareShiftBoundary,
    EstimateQubitFrequencyConfig,
    EstimateResonatorFrequencyConfig,
    Resonance,
    annotate_resonator_assignments,
    compute_coarse_control_amplitude,
    create_bare_shift_boundary_estimator,
    create_marked_figure,
    estimate_and_mark_qubit_figure,
    estimate_local_bare_shift_boundary,
    estimate_minimum_usable_power,
    estimate_optimal_powers,
    estimate_resonator_frequency_from_figure,
    guess_sorted_slots_for_partial_mux,
    mark_coarse_control_amplitude,
    peak_positions_from_assignment_order,
    remove_known_false_spikes_from_figure,
    resolve_resonator_assignment_order,
)
from qdash.api.schemas.reanalysis import (
    ReanalyzeOutputParameter,
    ReanalyzeQubitSpectroscopyParams,
    ReanalyzeResonatorSpectroscopyParams,
    ReanalyzeResponse,
)
from qdash.common.config.path_resolver import resolve_calib_data_path
from qdash.common.visualization.figure_metadata import FIGURE_ROLE_META_KEY
from qdash.dbmodel.task_result_history import TaskResultHistoryDocument

if TYPE_CHECKING:
    from collections.abc import Iterator

    import plotly.graph_objs as go

logger = logging.getLogger(__name__)


RESONATOR_TASK_NAME = "CheckResonatorSpectroscopy"
QUBIT_TASK_NAME = "CheckQubitSpectroscopy"
RAW_FIGURE_ROLE = "raw"
MARKED_FIGURE_ROLE = "marked"
PNG_MEDIA_TYPE = "image/png"
PREVIEW_IMAGE_ERROR = "Preview image rendering failed."


MAX_INLINE_LABEL_CHARS = 200
_INLINE_SIZE_RANGE = (100, 4000)
_TAG = re.compile(r"<[^>]*>")


def _inline_error(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=f"Invalid inline figure: {detail}")


def _is_finite_real(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        # A JSON integer beyond the float range, such as 10**309.
        return False


@cache
def _named_colorscales() -> frozenset[str]:
    """Plotly's named colorscales, lower case, each also reversed with the ``_r`` suffix."""
    import plotly.colors

    names = [name.lower() for name in plotly.colors.named_colorscales()]
    return frozenset([*names, *(f"{name}_r" for name in names)])


def _is_named_colorscale(value: Any) -> bool:
    return isinstance(value, str) and value.lower() in _named_colorscales()


def _finite_axis(trace: dict[str, Any], name: str) -> list[float]:
    values = trace.get(name)
    if isinstance(values, dict) and "bdata" in values:
        raise _inline_error(f"{name} uses a typed array (bdata); send a plain list of numbers.")
    if not isinstance(values, (list, tuple)):
        raise _inline_error(f"the heatmap's {name} must be a list of numbers.")
    if len(values) < 2:
        raise _inline_error(f"the heatmap's {name} needs at least 2 values.")
    if not all(_is_finite_real(value) for value in values):
        raise _inline_error(f"the heatmap's {name} must contain only finite numbers.")
    return [float(value) for value in values]


def _finite_grid(trace: dict[str, Any], rows: int, columns: int) -> list[list[float]]:
    values = trace.get("z")
    if isinstance(values, dict) and "bdata" in values:
        raise _inline_error("z uses a typed array (bdata); send a plain list of rows.")
    if not isinstance(values, (list, tuple)) or len(values) != rows:
        raise _inline_error("the heatmap's z must be a list with one row per y value.")
    grid: list[list[float]] = []
    for row in values:
        if not isinstance(row, (list, tuple)) or len(row) != columns:
            raise _inline_error("each row of the heatmap's z must have one value per x value.")
        if not all(_is_finite_real(value) for value in row):
            raise _inline_error("the heatmap's z must contain only finite numbers.")
        grid.append([float(value) for value in row])
    return grid


def _plain_label(value: Any) -> str | None:
    """A title's plain text, without markup, or None."""
    text = value.get("text") if isinstance(value, dict) else value
    if not isinstance(text, str):
        return None
    return _TAG.sub("", text)[:MAX_INLINE_LABEL_CHARS] or None


def _bounded_size(value: Any) -> int | None:
    low, high = _INLINE_SIZE_RANGE
    if _is_finite_real(value) and low <= value <= high:
        return int(value)
    return None


def _build_inline_figure(figure: dict[str, Any]) -> go.Figure:
    import plotly.graph_objects as pgo

    data = figure.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise _inline_error("data must be a non-empty list of traces.")
    trace = data[0]
    if trace.get("type") != "heatmap":
        raise _inline_error("the first trace must have type 'heatmap'.")
    xs = _finite_axis(trace, "x")
    ys = _finite_axis(trace, "y")
    zs = _finite_grid(trace, rows=len(ys), columns=len(xs))

    layout = figure.get("layout")
    layout = layout if isinstance(layout, dict) else {}
    meta = layout.get("meta")
    role = meta.get(FIGURE_ROLE_META_KEY, "") if isinstance(meta, dict) else ""
    if str(role).lower() == MARKED_FIGURE_ROLE:
        raise _inline_error("it is labeled as a marked figure; send the raw spectroscopy figure.")

    # The resonator assignment order runs in increasing frequency; analyze a descending
    # sweep as the same sweep in increasing order.
    if all(a > b for a, b in pairwise(xs)):
        xs = xs[::-1]
        zs = [row[::-1] for row in zs]

    heatmap: dict[str, Any] = {"x": xs, "y": ys, "z": zs}
    colorscale = trace.get("colorscale")
    if _is_named_colorscale(colorscale):
        heatmap["colorscale"] = colorscale
    colorbar = trace.get("colorbar")
    colorbar_title = _plain_label(colorbar.get("title")) if isinstance(colorbar, dict) else None
    if colorbar_title:
        heatmap["colorbar"] = {"title": {"text": colorbar_title}}

    safe_layout: dict[str, Any] = {}
    title = _plain_label(layout.get("title"))
    if title:
        safe_layout["title"] = {"text": title}
    for axis in ("xaxis", "yaxis"):
        settings = layout.get(axis)
        axis_title = _plain_label(settings.get("title")) if isinstance(settings, dict) else None
        if axis_title:
            safe_layout[axis] = {"title": {"text": axis_title}}
    for dimension in ("width", "height"):
        size = _bounded_size(layout.get(dimension))
        if size is not None:
            safe_layout[dimension] = size

    return pgo.Figure(data=[pgo.Heatmap(**heatmap)], layout=pgo.Layout(**safe_layout))


@contextmanager
def _analysis_errors(source: _ReanalysisSource) -> Iterator[None]:
    """Report an analysis that cannot run on an inline figure as HTTP 422.

    The estimators raise ``ValueError`` and similar on degenerate grids. For a
    caller's figure that is a bad request; the cause is logged, not returned.
    Errors on stored results keep propagating as before.
    """
    try:
        yield
    except HTTPException:
        raise
    except (ValueError, IndexError, ZeroDivisionError) as exc:
        if source.task_id is not None:
            raise
        logger.warning("Reanalysis of an inline %s figure failed", source.task_name, exc_info=True)
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid inline figure: the analysis could not run on this heatmap, "
                "for example because it has too few points or no usable signal."
            ),
        ) from exc


@dataclass(frozen=True)
class _ReanalysisSource:
    """What a reanalysis reads: a stored task result, or an inline figure (no ``task_id``)."""

    task_id: str | None
    task_name: str
    run_parameters: dict[str, Any]
    raw_figure: go.Figure


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
        figure: dict[str, Any] | None = None,
        include_image: bool = False,
    ) -> ReanalyzeResponse:
        """Re-run resonator-spectroscopy analysis with the given overrides.

        Mirrors ``CheckResonatorSpectroscopy.postprocess``: known instrument spikes
        are removed, the bare-shift boundary is estimated, and the optimal readout
        power and amplitude are derived for the requested qubit.
        """
        source = self._resolve_source(
            project_id=project_id,
            chip_id=chip_id,
            qid=qid,
            task_name=RESONATOR_TASK_NAME,
            source_task_id=source_task_id,
            figure=figure,
        )
        with _analysis_errors(source):
            return self._analyze_resonator(source, qid, params, include_image=include_image)

    def _analyze_resonator(
        self,
        source: _ReanalysisSource,
        qid: str,
        params: ReanalyzeResonatorSpectroscopyParams,
        *,
        include_image: bool,
    ) -> ReanalyzeResponse:
        run_parameters = source.run_parameters
        analysis_fig = remove_known_false_spikes_from_figure(source.raw_figure)

        config = self._build_resonator_config(params, run_parameters)

        # Older results stored analysis settings as run parameters. Newer results use
        # the task's internal analysis default when no explicit reanalysis override exists.
        estimator_type = params.bare_shift_estimator_type or self._stored_value(
            run_parameters,
            "bare_shift_estimator_type",
            default="high_frequency_strength",
        )
        if estimator_type and estimator_type != "config":
            strength_limit = params.bare_shift_strength_limit
            if strength_limit is None:
                stored_limit = self._stored_value(
                    run_parameters, "bare_shift_strength_limit", default=4.0
                )
                strength_limit = float(stored_limit) if stored_limit is not None else 4.0
            estimator = create_bare_shift_boundary_estimator(
                type=estimator_type,
                args={"strength_limit": strength_limit},
            )
            trace = analysis_fig.data[0]
            boundary = estimator.estimate_bare_shift_boundary(
                list(trace.x), list(trace.y), list(trace.z)
            )
            config = config.with_boundary(boundary)

        resonances, rejected, frequencies = estimate_resonator_frequency_from_figure(
            analysis_fig, config
        )

        trace = analysis_fig.data[0]
        xs = list(trace.x)
        local_boundaries, optimal_powers = self._estimate_resonator_powers(
            qid,
            list(trace.y),
            list(trace.z),
            config,
            resonances,
            rejected,
        )
        # Boundaries cover the selected resonances followed by the rejected ones;
        # optimal powers cover the selected ones, which come first.
        marked_fig = create_marked_figure(
            analysis_fig,
            resonances,
            rejected_resonances=rejected,
            local_boundaries=local_boundaries,
            optimal_powers=optimal_powers,
        )

        assignment_order = self._pick_resonator_assignment_order(params, run_parameters)
        resonance_index = self._resonance_index_for_qid(
            qid,
            xs,
            frequencies,
            assignment_order=assignment_order,
            marked_fig=marked_fig,
        )
        readout_frequency = (
            float(frequencies[resonance_index]) if resonance_index is not None else 0.0
        )
        outputs = [
            ReanalyzeOutputParameter(
                name="readout_frequency",
                value=readout_frequency,
                unit="GHz",
            )
        ]
        if (
            resonance_index is not None
            and optimal_powers is not None
            and resonance_index < len(optimal_powers)
        ):
            optimal_power = float(optimal_powers[resonance_index])
            outputs.append(
                ReanalyzeOutputParameter(name="optimal_power", value=optimal_power, unit="dB")
            )
            outputs.append(
                ReanalyzeOutputParameter(
                    name="readout_amplitude",
                    value=float(10 ** (optimal_power / 20)),
                    unit="a.u.",
                )
            )
        return self._build_response(source, qid, marked_fig, outputs, include_image=include_image)

    def reanalyze_qubit_spectroscopy(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
        params: ReanalyzeQubitSpectroscopyParams,
        source_task_id: str | None = None,
        figure: dict[str, Any] | None = None,
        include_image: bool = False,
    ) -> ReanalyzeResponse:
        """Re-run qubit-spectroscopy analysis with the given overrides.

        Mirrors ``CheckQubitSpectroscopy.postprocess``: besides the f01 estimate it
        returns the ``coarse_qubit_frequency`` and ``coarse_control_amplitude``
        seeds and draws the coarse amplitude on the marked figure.
        ``qubit_frequency`` is kept as an alias of the coarse f01 for existing
        callers.
        """
        source = self._resolve_source(
            project_id=project_id,
            chip_id=chip_id,
            qid=qid,
            task_name=QUBIT_TASK_NAME,
            source_task_id=source_task_id,
            figure=figure,
        )
        with _analysis_errors(source):
            return self._analyze_qubit(source, qid, params, include_image=include_image)

    def _analyze_qubit(
        self,
        source: _ReanalysisSource,
        qid: str,
        params: ReanalyzeQubitSpectroscopyParams,
        *,
        include_image: bool,
    ) -> ReanalyzeResponse:
        raw_fig = source.raw_figure

        config = self._build_qubit_config(params, source.run_parameters)
        retry_with_trim = bool(params.retry_with_trim)

        marked_fig, freq_result = estimate_and_mark_qubit_figure(
            raw_fig, config, retry_with_trim=retry_with_trim
        )

        outputs: list[ReanalyzeOutputParameter] = []
        if freq_result.f01 is not None:
            f01_frequency = float(freq_result.f01.frequency)
            repr_db = float(freq_result.f01.repr_db)
            coarse_control_amplitude, marker_db = compute_coarse_control_amplitude(repr_db)
            mark_coarse_control_amplitude(marked_fig, coarse_control_amplitude, marker_db)
            outputs.extend(
                [
                    ReanalyzeOutputParameter(
                        name="qubit_frequency", value=f01_frequency, unit="GHz"
                    ),
                    ReanalyzeOutputParameter(
                        name="coarse_qubit_frequency", value=f01_frequency, unit="GHz"
                    ),
                    ReanalyzeOutputParameter(
                        name="coarse_control_amplitude",
                        value=float(coarse_control_amplitude),
                        unit="a.u.",
                    ),
                    ReanalyzeOutputParameter(name="f01_repr_db", value=repr_db, unit="dB"),
                    ReanalyzeOutputParameter(
                        name="f01_quality_level",
                        value=float(freq_result.f01.quality_level),
                        unit="a.u.",
                    ),
                ]
            )
        if freq_result.anharmonicity is not None:
            outputs.append(
                ReanalyzeOutputParameter(
                    name="qubit_anharmonicity",
                    value=float(freq_result.anharmonicity),
                    unit="GHz",
                )
            )

        return self._build_response(source, qid, marked_fig, outputs, include_image=include_image)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _resolve_source(
        self,
        *,
        project_id: str,
        chip_id: str,
        qid: str,
        task_name: str,
        source_task_id: str | None,
        figure: dict[str, Any] | None,
    ) -> _ReanalysisSource:
        """The raw figure and stored run parameters to re-analyze.

        An inline ``figure`` is used as given with no stored run parameters;
        otherwise the stored task result is loaded.
        """
        if figure is not None:
            if source_task_id:
                raise HTTPException(
                    status_code=422,
                    detail="Give either source_task_id or figure, not both.",
                )
            return _ReanalysisSource(
                task_id=None,
                task_name=task_name,
                run_parameters={},
                raw_figure=self._parse_inline_figure(figure),
            )
        doc = self._load_source_doc(
            project_id=project_id,
            chip_id=chip_id,
            qid=qid,
            task_name=task_name,
            source_task_id=source_task_id,
        )
        return _ReanalysisSource(
            task_id=doc.task_id,
            task_name=doc.name,
            run_parameters=doc.run_parameters,
            raw_figure=self._load_raw_figure(doc),
        )

    @staticmethod
    def _parse_inline_figure(figure: dict[str, Any]) -> go.Figure:
        """Rebuild a caller's spectroscopy figure from its validated heatmap only.

        The caller's JSON is never handed to Plotly as is: rendering a figure can
        fetch resources it names (``layout.images``, templates), so only the numeric
        heatmap and a few plain-text labels are copied into a fresh figure. Anything
        else is dropped. Raises HTTP 422 unless the first trace is a raw heatmap of
        finite numbers on a grid of at least 2 x 2.
        """
        return _build_inline_figure(figure)

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

    @classmethod
    def _load_raw_figure(cls, doc: TaskResultHistoryDocument) -> go.Figure:
        """Load the raw (unmarked) Plotly figure of a spectroscopy task result.

        Spectroscopy tasks store the marked figure first and the raw figure second,
        so the raw figure is found by its ``raw`` filename suffix, then by its
        ``layout.meta`` figure role. A marked figure is never re-analyzed, even under a
        ``raw`` filename: when the raw figure cannot be identified or read, an HTTP
        error is raised.

        Records without role metadata predate the marked-first order and store the
        raw figure first, so their first figure is used when every figure is readable.
        """
        paths = [path for path in doc.json_figure_path or [] if path]
        if not paths:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Task result {doc.task_id!r} has no stored figure JSON; cannot re-analyze."
                ),
            )

        for path in paths:
            if cls._has_raw_filename(path):
                fig = cls._read_figure(doc, path)
                # The figure's own role wins over its filename.
                if cls._figure_role(fig) != MARKED_FIGURE_ROLE:
                    return fig

        loaded = [cls._try_read_figure(doc, path) for path in paths]
        figures = [item for item in loaded if not isinstance(item, HTTPException)]
        unreadable = [item for item in loaded if isinstance(item, HTTPException)]

        for fig in figures:
            if cls._figure_role(fig) == RAW_FIGURE_ROLE:
                return fig

        # The raw figure may be the one that could not be read; never fall back
        # to another figure, which may be the marked one.
        if unreadable:
            raise unreadable[0]

        if any(cls._figure_role(fig) is not None for fig in figures):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Task result {doc.task_id!r} has no raw figure (only marked or other "
                    "labeled figures); cannot re-analyze."
                ),
            )
        return figures[0]

    @staticmethod
    def _has_raw_filename(path: str) -> bool:
        """Whether a figure filename carries the ``raw`` role suffix (``Task_qid_raw_1``)."""
        return RAW_FIGURE_ROLE in Path(path).stem.lower().split("_")

    @staticmethod
    def _figure_role(fig: go.Figure) -> str | None:
        meta = getattr(fig.layout, "meta", None)
        if isinstance(meta, dict):
            role = meta.get(FIGURE_ROLE_META_KEY)
            if isinstance(role, str):
                return role.strip().lower()
        return None

    @classmethod
    def _try_read_figure(
        cls, doc: TaskResultHistoryDocument, path: str
    ) -> go.Figure | HTTPException:
        """Read a figure, returning the HTTP error instead of raising it."""
        try:
            return cls._read_figure(doc, path)
        except HTTPException as exc:
            return exc

    @staticmethod
    def _read_figure(doc: TaskResultHistoryDocument, path: str) -> go.Figure:
        import plotly.io as pio

        figure_path = resolve_calib_data_path(path)
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

    def _build_response(
        self,
        source: _ReanalysisSource,
        qid: str,
        marked_fig: go.Figure,
        outputs: list[ReanalyzeOutputParameter],
        *,
        include_image: bool,
    ) -> ReanalyzeResponse:
        image_base64: str | None = None
        image_media_type: str | None = None
        image_error: str | None = None
        if include_image:
            try:
                png = self._render_png(marked_fig)
            except Exception:
                logger.warning(
                    "Could not render reanalysis figure for task %s as PNG",
                    source.task_id or f"inline {source.task_name} figure",
                    exc_info=True,
                )
                # Renderer errors can name server paths; the details stay in the log.
                image_error = PREVIEW_IMAGE_ERROR
            else:
                image_base64 = base64.b64encode(png).decode("ascii")
                image_media_type = PNG_MEDIA_TYPE
        return ReanalyzeResponse(
            source_task_id=source.task_id,
            source_task_name=source.task_name,
            qid=qid,
            figure=self._figure_to_dict(marked_fig),
            output_parameters=outputs,
            image_base64=image_base64,
            image_media_type=image_media_type,
            image_error=image_error,
        )

    @staticmethod
    def _render_png(fig: go.Figure) -> bytes:
        """Render a figure to PNG bytes with Plotly's static image export (Kaleido)."""
        png = fig.to_image(format="png")
        if not isinstance(png, bytes) or not png:
            raise RuntimeError("Plotly returned no PNG data")
        return png

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
    def _pick_resonator_assignment_order(
        params: ReanalyzeResonatorSpectroscopyParams,
        stored_run_parameters: dict[str, Any],
    ) -> list[int]:
        if params.resonator_assignment_order is not None:
            return params.resonator_assignment_order

        stored_order = stored_run_parameters.get("resonator_assignment_order")
        if isinstance(stored_order, dict) and isinstance(stored_order.get("value"), list):
            return [int(offset) for offset in stored_order["value"]]

        # Read task results created before assignment orders were stored directly.
        pattern = None
        stored_pattern = stored_run_parameters.get("resonator_assignment_pattern")
        if isinstance(stored_pattern, dict) and "value" in stored_pattern:
            pattern = str(stored_pattern["value"])
        return list(resolve_resonator_assignment_order(pattern))

    @staticmethod
    def _estimate_resonator_powers(
        qid: str,
        ys: list[float],
        zs: list[list[float]],
        config: EstimateResonatorFrequencyConfig,
        resonances: list[Resonance],
        rejected: list[Resonance],
    ) -> tuple[list[BareShiftBoundary] | None, list[float] | None]:
        """Estimate local bare-shift boundaries and optimal powers as the workflow does.

        Returns ``(local_boundaries, optimal_powers)``; the boundaries cover the
        selected resonances followed by the rejected ones, and the optimal powers
        cover the selected ones. Both are ``None`` when the power analysis fails,
        so the frequency preview is still returned.
        """
        if not resonances and not rejected:
            return None, None
        try:
            minimum_usable_power = estimate_minimum_usable_power(
                ys,
                zs,
                config.low_power,
                correlation_coefficient_min=(
                    config.minimum_usable_power_correlation_coefficient_min
                ),
            )
            local_boundaries = [
                estimate_local_bare_shift_boundary(ys, resonance)
                for resonance in [*resonances, *rejected]
            ]
            optimal_powers = estimate_optimal_powers(
                ys,
                local_boundaries[: len(resonances)],
                minimum_usable_power,
            )
        except Exception:
            logger.warning(
                "Resonator power analysis failed during reanalysis for qid=%s",
                qid,
                exc_info=True,
            )
            return None, None
        return local_boundaries, optimal_powers

    @staticmethod
    def _resonance_index_for_qid(
        qid: str,
        xs: list[float],
        frequencies: list[float],
        *,
        assignment_order: list[int],
        marked_fig: go.Figure | None = None,
    ) -> int | None:
        """Return the index in ``frequencies`` of the requested qubit's resonance.

        Uses the workflow's assignment, including partial-MUX slot guessing. When
        ``marked_fig`` is given, each assigned resonance is labeled on it.
        """
        try:
            qid_int = int(qid)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"qid {qid!r} is not a valid integer qubit id."
            ) from exc
        if not frequencies:
            return None

        id_in_mux = qid_int % NUM_RESONATORS
        peak_positions = peak_positions_from_assignment_order(assignment_order)
        assigned_slot = peak_positions[id_in_mux]
        sorted_slots, assignment_mode = guess_sorted_slots_for_partial_mux(xs, frequencies)
        if marked_fig is not None:
            annotate_resonator_assignments(
                marked_fig,
                mux_index=qid_int // NUM_RESONATORS,
                sorted_slots=sorted_slots,
                frequencies=frequencies,
                peak_positions=peak_positions,
                assignment_mode=assignment_mode,
            )
        resonance_index = (
            sorted_slots.index(assigned_slot) if assigned_slot in sorted_slots else None
        )
        if resonance_index is not None and resonance_index < len(frequencies):
            return resonance_index

        logger.warning(
            "Resonator reanalysis for qid=%s produced %d frequencies (expected %d); "
            "assigned slot %d unavailable in mode %s.",
            qid,
            len(frequencies),
            NUM_RESONATORS,
            assigned_slot,
            assignment_mode,
        )
        return None
