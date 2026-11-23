"""Tests for the metrics PDF summary pagination."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from qdash.api.lib.metrics_pdf import (
    SUMMARY_FOOTER_Y,
    SUMMARY_TABLE_BOTTOM_LIMIT,
    MetricsPDFGenerator,
)
from qdash.api.schemas.metrics import ChipMetricsResponse, MetricValue
from qdash.common.config.metrics import load_metrics_config

if TYPE_CHECKING:
    import pytest

N_QUBITS = 4
COUPLING_KEYS = ("0-1", "1-0")


class RecordingCanvas(canvas.Canvas):
    """Canvas that records drawn text and rectangles per page."""

    def __init__(self) -> None:
        super().__init__(io.BytesIO(), pagesize=A4)
        self.pages: list[dict[str, list[Any]]] = []
        self._current: dict[str, list[Any]] = {"text": [], "rects": []}

    def _record_text(self, x: float, y: float, text: str) -> None:
        self._current["text"].append((x, y, text))

    def drawString(self, x, y, text, *args, **kwargs):
        self._record_text(x, y, text)
        return super().drawString(x, y, text, *args, **kwargs)

    def drawCentredString(self, x, y, text, *args, **kwargs):
        self._record_text(x, y, text)
        return super().drawCentredString(x, y, text, *args, **kwargs)

    def drawRightString(self, x, y, text, *args, **kwargs):
        self._record_text(x, y, text)
        return super().drawRightString(x, y, text, *args, **kwargs)

    def rect(self, x, y, width, height, stroke=1, fill=0):
        self._current["rects"].append((x, y, width, height, stroke, fill))
        return super().rect(x, y, width, height, stroke=stroke, fill=fill)

    def showPage(self):
        self.pages.append(self._current)
        self._current = {"text": [], "rects": []}
        return super().showPage()


def _metric_slots() -> list[tuple[str, str]]:
    """Return (metric_type, response key) for every configured metric in report order."""
    config = load_metrics_config()
    mapping = {"bare_frequency": "qubit_frequency"}
    slots = [("qubit", mapping.get(key, key)) for key in config.qubit_metrics]
    slots += [("coupling", key) for key in config.coupling_metrics]
    return slots


def _make_generator(populated: int) -> MetricsPDFGenerator:
    """Build a generator whose first ``populated`` metrics hold data.

    Each populated metric stores the value ``index / scale`` so that its
    summary median equals its report-order index.
    """
    config = load_metrics_config()
    mapping = {"bare_frequency": "qubit_frequency"}
    scales = {mapping.get(k, k): m.scale for k, m in config.qubit_metrics.items()}
    scales.update({k: m.scale for k, m in config.coupling_metrics.items()})
    qubit_metrics: dict[str, dict[str, MetricValue]] = {}
    coupling_metrics: dict[str, dict[str, MetricValue]] = {}
    for index, (metric_type, key) in enumerate(_metric_slots()[:populated]):
        value = MetricValue(value=index / scales[key])
        if metric_type == "qubit":
            qubit_metrics[key] = {str(q): value for q in range(N_QUBITS)}
        else:
            coupling_metrics[key] = dict.fromkeys(COUPLING_KEYS, value)
    response = ChipMetricsResponse(
        chip_id="TEST_CHIP",
        username="tester",
        qubit_count=N_QUBITS,
        qubit_metrics=qubit_metrics,
        coupling_metrics=coupling_metrics,
    )
    return MetricsPDFGenerator(response)


def _draw_summary(
    generator: MetricsPDFGenerator, monkeypatch: pytest.MonkeyPatch
) -> tuple[RecordingCanvas, list[list[dict[str, Any]]]]:
    """Draw the summary section, returning the canvas and the rows per page."""
    drawn_rows: list[list[dict[str, Any]]] = []
    original = generator._draw_summary_page

    def record(c, rows, page_index=1, page_count=1):
        drawn_rows.append(list(rows))
        return original(c, rows, page_index, page_count)

    monkeypatch.setattr(generator, "_draw_summary_page", record)
    c = RecordingCanvas()
    generator._draw_summary_pages(c)
    return c, drawn_rows


def _medians(drawn_rows: list[list[dict[str, Any]]]) -> list[float]:
    return [round(row["stats"]["median"]) for rows in drawn_rows for row in rows]


def _assert_page_layout(page: dict[str, list[Any]], footer_label: str) -> None:
    texts = [text for _, _, text in page["text"]]
    assert "Metrics Summary" in texts
    for header in ("Metric", "Unit", "Coverage", "Median", "Min", "Max"):
        assert header in texts
    assert "Chip: TEST_CHIP" in texts
    assert footer_label in texts
    # Only footer text may sit at or below the table bottom limit.
    for _, y, text in page["text"]:
        if y <= SUMMARY_TABLE_BOTTOM_LIMIT:
            assert y == SUMMARY_FOOTER_Y, text
    # The stroked outer border stays above the footer reservation.
    borders = [r for r in page["rects"] if r[4] == 1 and r[5] == 0]
    assert len(borders) == 1
    assert borders[0][1] >= SUMMARY_TABLE_BOTTOM_LIMIT


def test_summary_rows_per_page_fits_above_footer():
    generator = _make_generator(0)
    per_page = generator._summary_rows_per_page()
    assert per_page == 28


def test_summary_single_page(monkeypatch):
    generator = _make_generator(5)
    c, drawn_rows = _draw_summary(generator, monkeypatch)

    assert len(c.pages) == 1
    assert _medians(drawn_rows) == [0, 1, 2, 3, 4]
    _assert_page_layout(c.pages[0], "Summary")


def test_summary_exact_capacity_uses_one_page(monkeypatch):
    generator = _make_generator(0)
    capacity = generator._summary_rows_per_page()
    generator = _make_generator(capacity)
    c, drawn_rows = _draw_summary(generator, monkeypatch)

    assert len(c.pages) == 1
    assert _medians(drawn_rows) == list(range(capacity))
    _assert_page_layout(c.pages[0], "Summary")


def test_summary_overflow_all_populated_metrics(monkeypatch):
    total = len(_metric_slots())
    assert total == 34
    generator = _make_generator(total)
    capacity = generator._summary_rows_per_page()
    c, drawn_rows = _draw_summary(generator, monkeypatch)

    assert len(c.pages) == 2
    assert [len(rows) for rows in drawn_rows] == [capacity, total - capacity]
    # Order preserved, nothing dropped or duplicated.
    assert _medians(drawn_rows) == list(range(total))
    _assert_page_layout(c.pages[0], "Summary 1/2")
    _assert_page_layout(c.pages[1], "Summary 2/2")


def test_summary_without_metrics_keeps_one_page(monkeypatch):
    generator = _make_generator(0)
    c, drawn_rows = _draw_summary(generator, monkeypatch)

    assert len(c.pages) == 1
    assert drawn_rows == [[]]
    _assert_page_layout(c.pages[0], "Summary")


def test_paginate_summary_rows_has_no_blank_pages():
    generator = _make_generator(0)
    capacity = generator._summary_rows_per_page()
    rows = [{"id": i} for i in range(capacity * 2)]
    pages = generator._paginate_summary_rows(rows)
    assert [len(p) for p in pages] == [capacity, capacity]
    assert [r for p in pages for r in p] == rows
