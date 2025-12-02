"""Filesystem implementations of repository protocols.

This module provides concrete implementations of the CalibDataSaver protocol
using the local filesystem as the backend.
"""

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objs as go

logger = logging.getLogger(__name__)


class FilesystemCalibDataSaver:
    """Filesystem implementation of CalibDataSaver."""

    def __init__(self, calib_dir: str) -> None:
        """Initialize the saver with a calibration directory.

        Parameters
        ----------
        calib_dir : str
            The root calibration directory path

        """
        self.calib_dir = calib_dir

    def _resolve_conflict(self, path: Path) -> Path:
        """Resolve filename conflicts by appending a counter.

        Parameters
        ----------
        path : Path
            The original path that may conflict

        Returns
        -------
        Path
            A path that doesn't conflict with existing files

        """
        if not path.exists():
            return path

        base = path.stem
        ext = path.suffix
        parent = path.parent

        counter = 1
        while True:
            new_path = parent / f"{base}_{counter}{ext}"
            if not new_path.exists():
                return new_path
            counter += 1

    def _build_filename(
        self,
        task_name: str,
        task_type: str,
        qid: str,
        suffix: str,
        extension: str,
        index: int | None = None,
    ) -> str:
        """Build a standardized filename.

        Parameters
        ----------
        task_name : str
            The task name
        task_type : str
            The task type (qubit, coupling, global, system)
        qid : str
            The qubit ID
        suffix : str
            Optional suffix (e.g., for multiple figures)
        extension : str
            File extension (e.g., 'png', 'json', 'csv')
        index : int | None
            Optional index for multiple files

        Returns
        -------
        str
            The constructed filename

        """
        parts = [task_name]

        if task_type in ("qubit", "coupling") and qid:
            parts.append(qid)

        if suffix:
            parts.append(suffix)

        if index is not None:
            parts.append(str(index))

        return "_".join(parts) + f".{extension}"

    def save_figures(
        self,
        figures: list[go.Figure | go.FigureWidget],
        task_name: str,
        task_type: str,
        qid: str,
    ) -> tuple[list[str], list[str]]:
        """Save figures as PNG and JSON files.

        Parameters
        ----------
        figures : list
            List of plotly figures to save
        task_name : str
            The name of the task
        task_type : str
            The type of task (qubit, coupling, global, system)
        qid : str
            The qubit identifier (empty for global/system tasks)

        Returns
        -------
        tuple[list[str], list[str]]
            Tuple of (png_paths, json_paths)

        """
        if not figures:
            return [], []

        fig_dir = Path(self.calib_dir) / "fig"
        fig_dir.mkdir(parents=True, exist_ok=True)

        png_paths: list[str] = []
        json_paths: list[str] = []

        for i, fig in enumerate(figures):
            # Save PNG
            png_filename = self._build_filename(task_name, task_type, qid, "", "png", i)
            png_path = self._resolve_conflict(fig_dir / png_filename)
            fig.write_image(str(png_path))
            png_paths.append(str(png_path))

            # Save JSON
            json_filename = self._build_filename(task_name, task_type, qid, "", "json", i)
            json_path = self._resolve_conflict(fig_dir / json_filename)
            fig.write_json(str(json_path))
            json_paths.append(str(json_path))

        return png_paths, json_paths

    def save_raw_data(
        self,
        raw_data: list[np.ndarray],
        task_name: str,
        task_type: str,
        qid: str,
    ) -> list[str]:
        """Save raw data as CSV files.

        Parameters
        ----------
        raw_data : list
            List of numpy arrays to save
        task_name : str
            The name of the task
        task_type : str
            The type of task
        qid : str
            The qubit identifier

        Returns
        -------
        list[str]
            List of saved file paths

        """
        if not raw_data:
            return []

        raw_data_dir = Path(self.calib_dir) / "raw_data"
        raw_data_dir.mkdir(parents=True, exist_ok=True)

        paths: list[str] = []

        for i, data in enumerate(raw_data):
            csv_filename = self._build_filename(task_name, task_type, qid, "raw", "csv", i)
            csv_path = self._resolve_conflict(raw_data_dir / csv_filename)

            # Handle complex arrays
            if np.iscomplexobj(data):
                # Save as real, imag columns
                np.savetxt(
                    csv_path,
                    np.column_stack([data.real, data.imag]),
                    delimiter=",",
                )
            else:
                np.savetxt(csv_path, data, delimiter=",")

            paths.append(str(csv_path))

        return paths

    def save_task_json(self, task_id: str, task_data: dict) -> str:
        """Save task data as JSON.

        Parameters
        ----------
        task_id : str
            The task identifier
        task_data : dict
            The task data to save

        Returns
        -------
        str
            Path to the saved JSON file

        """
        task_dir = Path(self.calib_dir) / "task"
        task_dir.mkdir(parents=True, exist_ok=True)

        json_path = task_dir / f"{task_id}.json"
        with json_path.open("w") as f:
            json.dump(task_data, f, indent=2, default=str)

        return str(json_path)
