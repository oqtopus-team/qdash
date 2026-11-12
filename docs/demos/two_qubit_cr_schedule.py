"""Render the two-qubit CR schedule execution GIF for the docs.

The animation runs a schedule of seven directed CR pairs on a schematic four-MUX wiring with
``max_parallel_ops = 2``. ``GROUPS`` is the output of the QDash CR scheduler for ``PAIRS``,
``WIRING`` and ``MAX_PARALLEL_OPS``; the scheduler test
``tests/qdash/workflow/engine/scheduler/test_cr_schedule_docs_example.py`` recomputes it with
the scheduler code and fails if it drifts. ``docs/diagrams/cr-schedule-conflict-graph.svg``
draws the same fixture.

Groups run one after another. Inside a group every pair runs CheckCrossResonance, then
CreateZX90, then CheckZX90 in its own worker without waiting for the other pairs between
tasks; a pair that finishes early waits until every pair of its group is done. The durations
are illustrative units, not measurements.

The output is deterministic: the timeline is fixed below and the text uses the font bundled
with Pillow. Regenerate from the repository root with:

    uv run --no-project --with pillow==13.0.0 python3 docs/demos/two_qubit_cr_schedule.py

Pass ``--frames DIR`` to also write every frame as a PNG for review.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "public"
    / "images"
    / "guides"
    / "two-qubit-cr-schedule.gif"
)

# Schematic wiring: MUX n holds qubits 4n to 4n + 3. MUX1 and MUX2 share control module C1;
# every other module belongs to one MUX. Module names are illustrative.
WIRING = (
    {"mux": 0, "read_out": "R0:0", "ctrl": ["C0:0", "C0:1"]},
    {"mux": 1, "read_out": "R1:0", "ctrl": ["C1:0", "C1:1"]},
    {"mux": 2, "read_out": "R2:0", "ctrl": ["C1:2", "C1:3"]},
    {"mux": 3, "read_out": "R3:0", "ctrl": ["C3:0", "C3:1"]},
)
# Directed (control, target) pairs that already passed direction and coupling checks, in the
# order they are passed to CRScheduler.schedule_pairs().
PAIRS = (
    ("0", "1"),
    ("3", "1"),
    ("3", "2"),
    ("4", "5"),
    ("8", "9"),
    ("12", "13"),
    ("7", "10"),
)
MAX_PARALLEL_OPS = 2
# Scheduler output for the fixture above with the default largest_first coloring.
GROUPS = (
    (("0", "1"), ("4", "5")),
    (("12", "13"),),
    (("3", "1"), ("8", "9")),
    (("3", "2"),),
    (("7", "10"),),
)
# Conflict-graph color of each pair before max_parallel_ops splits a color into groups.
# The inter-MUX pair is colored in its own graph.
COLOR_CLASS = {
    ("0", "1"): "intra 1",
    ("4", "5"): "intra 1",
    ("12", "13"): "intra 1",
    ("3", "1"): "intra 2",
    ("8", "9"): "intra 2",
    ("3", "2"): "intra 3",
    ("7", "10"): "inter 1",
}

# The task list every pair runs in order: (task name, number drawn in the bar).
TASKS = (("CheckCrossResonance", "1"), ("CreateZX90", "2"), ("CheckZX90", "3"))
# Per-task durations in illustrative time units.
TASK_DURATIONS = {
    ("0", "1"): (2, 1, 1),
    ("4", "5"): (1, 1, 1),
    ("12", "13"): (1, 1, 1),
    ("3", "1"): (1, 1, 1),
    ("8", "9"): (2, 1, 2),
    ("3", "2"): (1, 1, 1),
    ("7", "10"): (1, 1, 1),
}

Pair = tuple[str, str]
Color = tuple[int, int, int]


@dataclass(frozen=True)
class Run:
    pair: Pair
    group: int  # 0-based index into GROUPS
    lane: int
    start: float
    end: float
    group_end: float

    def segments(self) -> list[tuple[int, float, float]]:
        parts, t = [], self.start
        for task, length in enumerate(TASK_DURATIONS[self.pair]):
            parts.append((task, t, t + length))
            t += length
        return parts

    def task_at(self, t: float) -> int | None:
        return next((task for task, a, b in self.segments() if a <= t < b), None)


def _runs() -> tuple[tuple[Run, ...], tuple[tuple[float, float], ...]]:
    runs, spans, t, lane = [], [], 0.0, 0
    for index, group in enumerate(GROUPS):
        end = t + max(sum(TASK_DURATIONS[pair]) for pair in group)
        for pair in group:
            runs.append(Run(pair, index, lane, t, t + sum(TASK_DURATIONS[pair]), end))
            lane += 1
        spans.append((t, end))
        t = end
    return tuple(runs), tuple(spans)


RUNS, SPANS = _runs()
T_END = SPANS[-1][1]

# Layout, in pixels. The docs column is about 728 px wide, so the canvas stays close to it.
WIDTH = 860
X0, X1 = 262, 844
UNIT = (X1 - X0) / T_END
AXIS_Y = 112
BAND_TOP = 120  # group labels
LANES_TOP = 146
LANE_STEP = 36
BAR_H = 24
LANES_BOTTOM = LANES_TOP + LANE_STEP * len(RUNS)
HEIGHT = LANES_BOTTOM + 196

INK = (31, 41, 55)
MUTED = (90, 100, 115)
GRID = (226, 230, 236)
BAND = (246, 247, 249)
QUEUED = (140, 148, 160)
WAITING = (180, 83, 9)
WAITING_BG = (254, 243, 199)
PLAYHEAD = (190, 18, 60)
WHITE = (255, 255, 255)
# Conflict-graph colors, shared with docs/diagrams/cr-schedule-conflict-graph.svg.
CLASS_COLOR: dict[str, Color] = {
    "intra 1": (37, 99, 235),
    "intra 2": (13, 148, 136),
    "intra 3": (124, 58, 237),
    "inter 1": (190, 24, 93),
}


def _tint(color: Color, amount: float) -> Color:
    r, g, b = color
    return (
        round(r + (255 - r) * amount),
        round(g + (255 - g) * amount),
        round(b + (255 - b) * amount),
    )


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


F_TITLE, F_HEAD, F_TEXT, F_SMALL = _font(21), _font(16), _font(15), _font(13)


def _x(t: float) -> float:
    return X0 + t * UNIT


def _lane_y(lane: int) -> float:
    return LANES_TOP + lane * LANE_STEP + (LANE_STEP - BAR_H) / 2


def _pair_name(pair: Pair) -> str:
    return f"{pair[0]}->{pair[1]}"


def _draw_pair(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    pair: Pair,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    color: Color,
) -> float:
    """Draw ``control -> target`` with a drawn arrow; the bundled font has no arrow glyph."""
    draw.text((x, y), pair[0], font=font, fill=color)
    x += draw.textlength(pair[0], font=font) + 3
    size = getattr(font, "size", 15)
    mid = y + size * 0.62
    draw.line([(x, mid), (x + 13, mid)], fill=color, width=2)
    draw.polygon([(x + 16, mid), (x + 10, mid - 4), (x + 10, mid + 4)], fill=color)
    x += 19
    draw.text((x, y), pair[1], font=font, fill=color)
    return x + draw.textlength(pair[1], font=font)


def _draw_rich(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    color: Color,
) -> None:
    """Draw text, replacing each ``control->target`` token with a drawn pair arrow."""
    for part in re.split(r"(\d+->\d+)", text):
        if re.fullmatch(r"\d+->\d+", part):
            control, target = part.split("->")
            x = _draw_pair(draw, x, y, (control, target), font, color)
        elif part:
            draw.text((x, y), part, font=font, fill=color)
            x += draw.textlength(part, font=font)


def _dashed_rect(draw: ImageDraw.ImageDraw, box: tuple[float, ...], color: Color) -> None:
    x0, y0, x1, y1 = box
    dash = 5
    x = x0
    while x < x1:
        draw.line([(x, y0), (min(x + dash, x1), y0)], fill=color, width=2)
        draw.line([(x, y1), (min(x + dash, x1), y1)], fill=color, width=2)
        x += dash * 2
    y = y0
    while y < y1:
        draw.line([(x0, y), (x0, min(y + dash, y1))], fill=color, width=2)
        draw.line([(x1, y), (x1, min(y + dash, y1))], fill=color, width=2)
        y += dash * 2


def _hatch(draw: ImageDraw.ImageDraw, box: tuple[float, ...], color: Color) -> None:
    x0, y0, x1, y1 = box
    step = 8
    offset = 0.0
    while x0 + offset - (y1 - y0) < x1:
        ax, ay = x0 + offset, y0
        bx, by = x0 + offset - (y1 - y0), y1
        if ax > x1:
            ay += ax - x1
            ax = x1
        if bx < x0:
            by -= x0 - bx
            bx = x0
        if ay <= y1 and by >= y0:
            draw.line([(ax, ay), (bx, by)], fill=color, width=1)
        offset += step


def _vdash(draw: ImageDraw.ImageDraw, x: float, y0: float, y1: float, color: Color) -> None:
    y = y0
    while y < y1:
        draw.line([(x, y), (x, min(y + 5, y1))], fill=color, width=2)
        y += 9


def _draw_run(draw: ImageDraw.ImageDraw, run: Run, t: float) -> None:
    color = CLASS_COLOR[COLOR_CLASS[run.pair]]
    y0 = _lane_y(run.lane)
    y1 = y0 + BAR_H
    # A pair that finished its list waits for the rest of its group.
    if run.end < run.group_end and t > run.end:
        box = (_x(run.end) + 1, y0 + 4, _x(min(t, run.group_end)) - 1, y1 - 4)
        if box[2] > box[0]:
            draw.rectangle(box, fill=WAITING_BG)
            _hatch(draw, box, WAITING)
    for task, a, b in run.segments():
        box = (_x(a) + 1, y0, _x(b) - 1, y1)
        if t >= b:
            draw.rectangle(box, fill=_tint(color, 0.8), outline=color, width=2)
            text_color, plate = color, _tint(color, 0.8)
        elif t >= a:
            draw.rectangle(box, fill=WHITE)
            progress = (box[0], y0, _x(t), y1)
            if progress[2] > progress[0]:
                draw.rectangle(progress, fill=_tint(color, 0.85))
                _hatch(draw, progress, color)
            draw.rectangle(box, outline=color, width=3)
            text_color, plate = color, WHITE
        else:
            _dashed_rect(draw, box, QUEUED)
            text_color, plate = QUEUED, WHITE
        label = TASKS[task][1]
        width = draw.textlength(label, font=F_SMALL)
        tx = (box[0] + box[2] - width) / 2
        ty = y0 + (BAR_H - 14) / 2
        draw.rectangle((tx - 3, ty - 1, tx + width + 3, ty + 14), fill=plate)
        draw.text((tx, ty), label, font=F_SMALL, fill=text_color)


def _readout(run: Run, t: float) -> tuple[str, Color]:
    task = run.task_at(t)
    if task is not None:
        return TASKS[task][0], CLASS_COLOR[COLOR_CLASS[run.pair]]
    if t < run.start:
        return "queued", QUEUED
    if t < run.group_end:
        return "waits for group", WAITING
    return "done", MUTED


def _current_group(t: float) -> int:
    return next((i for i, (a, b) in enumerate(SPANS) if a <= t < b), len(SPANS))


def _status(t: float) -> tuple[str, str]:
    """Return two lines that name what the frame shows."""
    group = _current_group(t)
    running = {
        _pair_name(r.pair): TASKS[r.task_at(t) or 0][0] for r in RUNS if r.task_at(t) is not None
    }
    waiting = [r for r in RUNS if r.group == group and r.end <= t < r.group_end]
    if t == 0:
        return (
            "Group 1 starts: pairs 0->1 and 4->5 run in separate workers.",
            "Every other group is queued until the group before it is done.",
        )
    if group == len(SPANS):
        return (
            f"All {len(GROUPS)} groups done at t = {T_END:g}.",
            "Each group started only after every pair of the group before it finished.",
        )
    if waiting:
        w = waiting[0]
        peers = [r for r in RUNS if r.group == group and r.task_at(t) is not None]
        peer = peers[0]
        return (
            f"{_pair_name(w.pair)} finished all three tasks and waits for "
            f"{_pair_name(peer.pair)}, still on {TASKS[peer.task_at(t) or 0][0]}.",
            f"Group {group + 2} starts only when every pair of group {group + 1} is done.",
        )
    if group == 0 and len(set(running.values())) > 1:
        return (
            f"4->5 is on {running['4->5']} while 0->1 is still on {running['0->1']}.",
            "Pairs do not wait for each other between tasks.",
        )
    if group == 1:
        return (
            "Group 2: 12->13 conflicts with no pair, yet runs alone.",
            "Its graph color has three pairs; max_parallel_ops = 2 split them into two groups.",
        )
    if group == 2:
        return (
            "Group 3: 3->1 and 8->9 share the second color of the conflict graph.",
            "3->1 shares qubit 1 with 0->1; 8->9 shares control module C1 with 4->5.",
        )
    if group == 3:
        return (
            "Group 4: 3->2 shares qubit 3 with 3->1 and MUX0 with 0->1,",
            "so it needs a third color and runs alone.",
        )
    if group == 4:
        return (
            "Group 5: the inter-MUX pair 7->10 runs after every intra-MUX group.",
            "Inter-MUX pairs are colored in their own conflict graph.",
        )
    return ("", "")


def render(t: float) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(image)
    draw.text((16, 10), "Two-qubit CR schedule: running the groups", font=F_TITLE, fill=INK)
    draw.text(
        (16, 40),
        f"max_parallel_ops = {MAX_PARALLEL_OPS}. Groups run in order; the pairs of a group run "
        "in separate workers.",
        font=F_TEXT,
        fill=INK,
    )
    draw.text(
        (16, 62),
        "Every pair runs its own list: 1 CheckCrossResonance, 2 CreateZX90, 3 CheckZX90.",
        font=F_TEXT,
        fill=MUTED,
    )

    # Time axis.
    for tick in range(int(T_END) + 1):
        x = _x(tick)
        draw.line([(x, AXIS_Y - 6), (x, AXIS_Y)], fill=MUTED, width=1)
        if tick % 2 == 0:
            label = str(tick)
            draw.text(
                (x - draw.textlength(label, font=F_SMALL) / 2, AXIS_Y - 22),
                label,
                font=F_SMALL,
                fill=MUTED,
            )
    draw.text((16, AXIS_Y - 22), "time (illustrative)", font=F_SMALL, fill=MUTED)

    # Group bands, labels and boundaries.
    for index, (a, b) in enumerate(SPANS):
        if index % 2 == 0:
            draw.rectangle((_x(a), BAND_TOP, _x(b), LANES_BOTTOM), fill=BAND)
        label = f"Group {index + 1}"
        active = _current_group(t) == index
        font = F_HEAD if active else F_TEXT
        width = draw.textlength(label, font=font)
        draw.text(
            ((_x(a) + _x(b) - width) / 2, BAND_TOP + 3),
            label,
            font=font,
            fill=INK if active else MUTED,
        )
    draw.text((16, BAND_TOP + 4), "pair", font=F_SMALL, fill=MUTED)
    draw.text((104, BAND_TOP + 4), "current task", font=F_SMALL, fill=MUTED)
    for tick in range(int(T_END) + 1):
        draw.line([(_x(tick), LANES_TOP), (_x(tick), LANES_BOTTOM)], fill=GRID, width=1)
    for a, _ in SPANS[1:]:
        _vdash(draw, _x(a), BAND_TOP, LANES_BOTTOM + 4, INK)
    # Intra/inter bracket under the lanes.
    intra_end = SPANS[-2][1]
    by = LANES_BOTTOM + 8
    draw.line([(_x(0) + 2, by), (_x(intra_end) - 3, by)], fill=MUTED, width=2)
    draw.line([(_x(intra_end) + 3, by), (_x(T_END) - 2, by)], fill=MUTED, width=2)
    draw.text((_x(0) + 4, by + 4), "intra-MUX groups first", font=F_SMALL, fill=MUTED)
    label = "inter-MUX"
    draw.text(
        (_x(T_END) - draw.textlength(label, font=F_SMALL) - 2, by + 4),
        label,
        font=F_SMALL,
        fill=MUTED,
    )

    # Pair names and current task.
    for run in RUNS:
        y = _lane_y(run.lane)
        color = CLASS_COLOR[COLOR_CLASS[run.pair]]
        draw.rectangle((16, y + 5, 28, y + 17), fill=color)
        _draw_pair(draw, 34, y + 3, run.pair, F_HEAD, INK)
        text, text_color = _readout(run, t)
        draw.text((104, y + 5), text, font=F_SMALL, fill=text_color)
        _draw_run(draw, run, t)

    # Playhead.
    x = _x(t)
    draw.line([(x, BAND_TOP + 22), (x, LANES_BOTTOM + 4)], fill=PLAYHEAD, width=2)
    label = f"t = {t:g}"
    width = draw.textlength(label, font=F_SMALL)
    lx = min(max(x - width / 2, X0), X1 - width)
    draw.rectangle((lx - 3, AXIS_Y - 23, lx + width + 3, AXIS_Y - 6), fill=PLAYHEAD)
    draw.text((lx, AXIS_Y - 22), label, font=F_SMALL, fill=WHITE)

    # Status.
    sy = LANES_BOTTOM + 34
    first, second = _status(t)
    _draw_rich(draw, 16, sy, first, F_TEXT, INK)
    _draw_rich(draw, 16, sy + 21, second, F_TEXT, INK)

    # Legend.
    ly = sy + 56
    lx = 16.0
    entries = (
        ("not started", "queued"),
        ("running", "running"),
        ("done", "done"),
        ("waits for its group", "wait"),
    )
    sample = CLASS_COLOR["intra 1"]
    for text, kind in entries:
        box = (lx, ly, lx + 30, ly + 16)
        if kind == "queued":
            _dashed_rect(draw, box, QUEUED)
        elif kind == "running":
            draw.rectangle(box, fill=_tint(sample, 0.85))
            _hatch(draw, box, sample)
            draw.rectangle(box, outline=sample, width=2)
        elif kind == "done":
            draw.rectangle(box, fill=_tint(sample, 0.8), outline=sample, width=2)
        else:
            draw.rectangle(box, fill=WAITING_BG)
            _hatch(draw, box, WAITING)
        draw.text((lx + 38, ly + 1), text, font=F_TEXT, fill=INK)
        lx += 38 + draw.textlength(text, font=F_TEXT) + 24
    draw.text(
        (16, ly + 26),
        "Square color = the pair's conflict-graph color. Groups 1 and 2 share a color: the cap split it.",
        font=F_SMALL,
        fill=MUTED,
    )
    draw.text(
        (16, ly + 44),
        "Illustrative durations, not a benchmark, and no pulse synchronization between pairs.",
        font=F_SMALL,
        fill=MUTED,
    )
    draw.text(
        (16, ly + 62),
        "max_parallel_ops caps pairs per group; it does not guarantee that many workers run at once.",
        font=F_SMALL,
        fill=MUTED,
    )
    return image


# (time, hold in ms). Pauses sit on the moments the docs describe: different tasks at the same
# time (1.5), a finished pair waiting for its group (3.5, 10.5), each later group, and the end.
HOLDS = {
    0.0: 1600,
    1.5: 2800,
    3.5: 3000,
    5.5: 2600,
    8.5: 2200,
    10.5: 3000,
    13.5: 2400,
    16.5: 2400,
    18.0: 3400,
}


def timeline() -> list[tuple[float, int]]:
    steps = [round(i * 0.5, 1) for i in range(int(T_END / 0.5) + 1)]
    return [(t, HOLDS.get(t, 220)) for t in steps]


def _check() -> None:
    """Fail fast if the fixture drifts from what the docs state."""
    scheduled = [pair for group in GROUPS for pair in group]
    assert sorted(scheduled) == sorted(PAIRS), scheduled
    assert all(len(group) <= MAX_PARALLEL_OPS for group in GROUPS)
    assert set(COLOR_CLASS) == set(PAIRS) == set(TASK_DURATIONS)
    assert SPANS == ((0, 4), (4, 7), (7, 12), (12, 15), (15, 18)), SPANS


def build(output: Path, frames_dir: Path | None) -> None:
    _check()
    frames = [(render(t), hold) for t, hold in timeline()]
    # One shared palette keeps colors stable between frames and the file small.
    palette_source = frames[len(frames) // 2][0].quantize(
        colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )
    quantized = [
        image.quantize(palette=palette_source, dither=Image.Dither.NONE) for image, _ in frames
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        output,
        save_all=True,
        append_images=quantized[1:],
        duration=[hold for _, hold in frames],
        loop=0,
        optimize=True,
        disposal=1,
    )
    if frames_dir is not None:
        frames_dir.mkdir(parents=True, exist_ok=True)
        for (t, _), (image, _) in zip(timeline(), frames, strict=True):
            image.save(frames_dir / f"t{t:04.1f}.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--frames", type=Path, default=None, help="Also write PNG frames here")
    args = parser.parse_args()
    build(args.output, args.frames)
    print(f"Wrote {args.output} ({args.output.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
