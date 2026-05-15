"""Support loaders for small facade-oriented Copilot helpers."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from qdash.common.utils.json import sanitize_for_json

if TYPE_CHECKING:
    import logging


class CopilotSupportDataAccessProtocol(Protocol):
    """Subset of data-access methods used by support helpers."""

    def load_latest_installed_chip(self) -> Any | None: ...

    def load_qubit(self, chip_id: str, qid: str) -> Any | None: ...

    def load_task_result(self, task_id: str) -> Any | None: ...

    def load_distinct_output_parameter_names(
        self, chip_id: str, qid: str | None
    ) -> list[str] | None: ...

    def load_output_parameter_name_fallback_docs(
        self, chip_id: str, qid: str | None
    ) -> list[Any]: ...


class CopilotSupportService:
    """Small support helpers used by the Copilot facade and analysis flow."""

    def __init__(
        self,
        *,
        data_access: CopilotSupportDataAccessProtocol,
        logger: logging.Logger,
        max_figure_size: int,
    ) -> None:
        self._data_access = data_access
        self._logger = logger
        self._max_figure_size = max_figure_size

    def load_default_chip_id(self) -> str | None:
        """Load the most recently installed chip_id from DB."""
        doc = self._data_access.load_latest_installed_chip()
        if doc is None:
            return None
        return str(doc.chip_id)

    def load_qubit_params(self, chip_id: str, qid: str) -> dict[str, Any]:
        """Load current qubit parameters from DB."""
        doc = self._data_access.load_qubit(chip_id, qid)
        if doc is None:
            return {}
        return cast("dict[str, Any]", sanitize_for_json(dict(doc.data)))

    def load_task_result(self, task_id: str) -> dict[str, Any] | None:
        """Load task result from DB."""
        doc = self._data_access.load_task_result(task_id)
        if doc is None:
            return None
        return {
            "input_parameters": doc.input_parameters or {},
            "output_parameters": doc.output_parameters or {},
            "run_parameters": getattr(doc, "run_parameters", {}) or {},
            "figure_path": getattr(doc, "figure_path", []) or [],
        }

    def load_figure_as_base64(self, figure_paths: list[str]) -> str | None:
        """Read the first existing PNG file from figure_paths and return base64."""
        images = self.load_figures_as_base64(figure_paths)
        return images[0][0] if images else None

    def load_figures_as_base64(self, figure_paths: list[str]) -> list[tuple[str, str]]:
        """Read existing PNG figures and return labeled target images."""
        images: list[tuple[str, str]] = []
        for figure_path in figure_paths:
            path = Path(figure_path)
            if path.is_file() and path.suffix.lower() == ".png":
                if path.stat().st_size > self._max_figure_size:
                    self._logger.warning("Figure %s exceeds 5MB size limit, skipping", figure_path)
                    continue
                role = self._target_figure_role(path, len(images))
                images.append((base64.b64encode(path.read_bytes()).decode("ascii"), role))
        return images

    @staticmethod
    def _target_figure_role(path: Path, index: int) -> str:
        """Infer the target figure role from filename suffixes, falling back to order."""
        stem = path.stem.lower()
        if "marked" in stem:
            return "target marked result image; validate heuristic markers against the raw signal"
        if "raw" in stem:
            return "target raw result image; inspect the measured signal without overlays"
        if index == 0:
            return "target raw result image; inspect the measured signal without overlays"
        if index == 1:
            return "target marked result image; validate heuristic markers against the raw signal"
        return f"target supporting result image {index + 1}"

    @staticmethod
    def collect_expected_images(
        knowledge: Any,
        max_images: int | None = None,
    ) -> list[tuple[str, str]]:
        """Collect expected reference images from TaskKnowledge."""
        if knowledge is None:
            return []
        result = [(img.base64_data, img.alt_text) for img in knowledge.images if img.base64_data]
        for case in knowledge.cases:
            for img in case.images:
                if img.base64_data:
                    result.append((img.base64_data, f"[Case: {case.title}] {img.alt_text}"))
        if max_images is not None and max_images >= 0:
            return result[:max_images]
        return result

    def load_available_parameters(
        self,
        chip_id: str,
        qid: str | None = None,
    ) -> dict[str, Any]:
        """List distinct output parameter names recorded for a chip."""
        try:
            names = self._data_access.load_distinct_output_parameter_names(chip_id, qid)
        except (AttributeError, TypeError) as error:
            self._logger.warning("distinct() failed for output_parameter_names: %s", error)
            docs = self._data_access.load_output_parameter_name_fallback_docs(chip_id, qid)
            name_set: set[str] = set()
            for doc in docs:
                if doc.output_parameter_names:
                    name_set.update(doc.output_parameter_names)
            names = sorted(name_set)

        if not names:
            return {
                "error": f"No output parameters found for chip_id={chip_id}"
                + (f", qid={qid}" if qid else "")
            }

        return {
            "chip_id": chip_id,
            "qid": qid,
            "parameter_names": sorted(names),
            "count": len(names),
        }

    @staticmethod
    def build_images_sent_metadata(
        image_base64: str | None,
        figure_paths: list[str],
        expected_images: list[tuple[str, str]],
        task_name: str,
        experiment_images: list[tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Build the ``images_sent`` metadata dict for analysis responses."""
        return {
            "experiment_figure": bool(experiment_images or image_base64),
            "experiment_figure_paths": figure_paths if experiment_images or image_base64 else [],
            "experiment_images": [
                {"alt_text": alt, "index": i} for i, (_, alt) in enumerate(experiment_images or [])
            ],
            "expected_images": [
                {"alt_text": alt, "index": i} for i, (_, alt) in enumerate(expected_images)
            ],
            "task_name": task_name,
        }
