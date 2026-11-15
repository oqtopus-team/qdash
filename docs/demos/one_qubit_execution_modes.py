"""Render the one-qubit execution mode comparison GIF for the docs and the editor help.

The animation compares ``sequential``, ``parallel_by_mux`` and ``parallel_by_round``
on the same illustrative selection: Q0 and Q1 on MUX0, Q8 and Q9 on MUX2, both MUXes
in the same box stage. Every qubit runs the same task list, CheckRabi, then
CreateHPIPulse, then CheckT1; each bar is split into those tasks. The durations are
illustrative units, not measurements. The rounds are {Q0, Q8} then {Q1, Q9}, and a
round waits for each qubit's whole task list, not for each task.

The output is deterministic: the timeline is fixed below and the text uses the font
bundled with Pillow. Besides the docs GIF, the script writes a copy of the GIF and a
still poster frame to ``ui/public/images/execution-help/`` for the workflow editor's
Execution help dialog. Regenerate from the repository root with:

    uv run --no-project --with pillow==13.0.0 python3 docs/demos/one_qubit_execution_modes.py

Pass ``--frames DIR`` to also write every frame as a PNG for review.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "public"
    / "images"
    / "guides"
    / "one-qubit-execution-modes.gif"
)
# The workflow editor's Execution help dialog serves these from the UI bundle.
UI_DIR = Path(__file__).resolve().parents[2] / "ui" / "public" / "images" / "execution-help"

# The task list every qubit runs in order: (task name, short label drawn in the bar).
TASKS = (("CheckRabi", "Rabi"), ("CreateHPIPulse", "HPI"), ("CheckT1", "T1"))
# Per-task durations in illustrative time units. The totals are Q0 3, Q1 4, Q8 5, Q9 3:
# Q0 is shorter than Q8, so under parallel_by_mux Q1 starts while Q8 is still on CheckT1,
# and Q8's CheckRabi is longer, so Q0 reaches CreateHPIPulse while Q8 is still on CheckRabi.
TASK_DURATIONS = {"Q0": (1, 1, 1), "Q1": (1, 1, 2), "Q8": (2, 1, 2), "Q9": (1, 1, 1)}
DURATION = {qid: sum(parts) for qid, parts in TASK_DURATIONS.items()}
LANES = (("MUX0", ("Q0", "Q1")), ("MUX2", ("Q8", "Q9")))
T_END = 15


@dataclass(frozen=True)
class Segment:
    task: int  # index into TASKS
    start: float
    end: float


@dataclass(frozen=True)
class Run:
    qid: str
    lane: int
    start: float
    end: float
    # Earliest time the qubit's MUX could have started it; earlier than ``start``
    # only when the qubit waits for a round.
    ready: float

    @property
    def segments(self) -> tuple[Segment, ...]:
        parts, t = [], self.start
        for task, length in enumerate(TASK_DURATIONS[self.qid]):
            parts.append(Segment(task, t, t + length))
            t += length
        return tuple(parts)

    def task_at(self, t: float) -> int | None:
        return next((s.task for s in self.segments if s.start <= t < s.end), None)


@dataclass(frozen=True)
class Mode:
    name: str
    rule: str
    runs: tuple[Run, ...]
    barriers: tuple[float, ...] = ()


def _lane(qid: str) -> int:
    return next(index for index, (_, qids) in enumerate(LANES) if qid in qids)


def _sequential() -> Mode:
    runs, t = [], 0.0
    for qid in ("Q0", "Q1", "Q8", "Q9"):  # MUX0 then MUX2, one qubit at a time
        runs.append(Run(qid, _lane(qid), t, t + DURATION[qid], t))
        t += DURATION[qid]
    return Mode("sequential", "One MUX at a time, one qubit at a time", tuple(runs))


def _parallel_by_mux() -> Mode:
    runs = []
    for lane, (_, qids) in enumerate(LANES):
        t = 0.0
        for qid in qids:  # each MUX moves on as soon as its current qubit finishes
            runs.append(Run(qid, lane, t, t + DURATION[qid], t))
            t += DURATION[qid]
    return Mode(
        "parallel_by_mux",
        "Each MUX starts its next qubit when the current one is done",
        tuple(runs),
    )


def _parallel_by_round() -> Mode:
    runs, t = [], 0.0
    barriers = []
    lane_free = [0.0, 0.0]
    for number, round_qids in enumerate((("Q0", "Q8"), ("Q1", "Q9")), start=1):
        for qid in round_qids:
            lane = _lane(qid)
            runs.append(Run(qid, lane, t, t + DURATION[qid], lane_free[lane]))
            lane_free[lane] = t + DURATION[qid]
        if number > 1:
            barriers.append(t)
        t = max(t + DURATION[qid] for qid in round_qids)
    return Mode(
        "parallel_by_round",
        "The next round starts when every qubit of the round is done",
        tuple(runs),
        tuple(barriers),
    )


MODES = (_sequential(), _parallel_by_mux(), _parallel_by_round())

# Layout, in pixels. The docs column is about 728 px wide, so the canvas stays close to it.
WIDTH, HEIGHT = 860, 792
X0, X1 = 196, 838
UNIT = (X1 - X0) / T_END
HEADER = 104
PANEL = 188  # title, two lanes, a round-label row and a status line
TITLE_H = 30  # panel title row
TAB_H = 16  # qubit name above each bar
LANE_H = 30
LANE_STEP = TAB_H + LANE_H + 8

INK = (31, 41, 55)
MUTED = (90, 100, 115)
GRID = (226, 230, 236)
QUEUED = (120, 128, 140)
WAITING = (180, 83, 9)
WAITING_BG = (254, 243, 199)
RUNNING = (29, 78, 216)
RUNNING_BG = (219, 234, 254)
DONE = (21, 128, 61)
DONE_BG = (220, 252, 231)
PLAYHEAD = (190, 18, 60)
WHITE = (255, 255, 255)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


F_TITLE, F_HEAD, F_TEXT, F_SMALL = _font(21), _font(17), _font(15), _font(13)


def _x(t: float) -> float:
    return X0 + t * UNIT


def _bar_top(top: float, lane: int) -> float:
    return top + TITLE_H + lane * LANE_STEP + TAB_H


def _dashed_rect(draw: ImageDraw.ImageDraw, box: tuple[float, ...], color: tuple[int, ...]) -> None:
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


def _hatch(draw: ImageDraw.ImageDraw, box: tuple[float, ...], color: tuple[int, ...]) -> None:
    x0, y0, x1, y1 = box
    step = 8
    offset = 0.0
    while x0 + offset - (y1 - y0) < x1:
        ax, ay = x0 + offset, y0
        bx, by = x0 + offset - (y1 - y0), y1
        # Clip the diagonal to the box.
        if ax > x1:
            ay += ax - x1
            ax = x1
        if bx < x0:
            by -= x0 - bx
            bx = x0
        if ay <= y1 and by >= y0:
            draw.line([(ax, ay), (bx, by)], fill=color, width=1)
        offset += step


def _state(run: Run, t: float) -> str:
    if t >= run.end:
        return "done"
    if t >= run.start:
        return "running"
    if t >= run.ready and run.start > run.ready:
        return "waiting"
    return "queued"


def _segment_state(run: Run, segment: Segment, t: float) -> str:
    if t >= segment.end:
        return "done"
    if t >= segment.start:
        return "running"
    return "waiting" if _state(run, t) == "waiting" else "queued"


Color = tuple[int, int, int]
Label = tuple[float, float, str, Color, Color]


def _draw_run(draw: ImageDraw.ImageDraw, run: Run, top: float, t: float) -> list[Label]:
    """Draw one qubit's bar, split into its tasks, and return the labels to draw on top."""
    y0 = _bar_top(top, run.lane)
    y1 = y0 + LANE_H
    labels: list[Label] = []
    for segment in run.segments:
        box = (_x(segment.start) + 1, y0, _x(segment.end) - 1, y1)
        state = _segment_state(run, segment, t)
        if state == "done":
            draw.rectangle(box, fill=DONE_BG, outline=DONE, width=2)
            color, plate = DONE, DONE_BG
        elif state == "running":
            draw.rectangle(box, fill=WHITE)
            progress = (box[0], y0, _x(t), y1)
            if progress[2] > progress[0]:
                draw.rectangle(progress, fill=RUNNING_BG)
                _hatch(draw, progress, RUNNING)
            draw.rectangle(box, outline=RUNNING, width=3)
            color, plate = RUNNING, WHITE
        else:
            _dashed_rect(draw, box, WAITING if state == "waiting" else QUEUED)
            color, plate = (WAITING if state == "waiting" else QUEUED), WHITE
        text = TASKS[segment.task][1]
        width = draw.textlength(text, font=F_SMALL)
        labels.append(((box[0] + box[2] - width) / 2, y0 + (LANE_H - 14) / 2, text, color, plate))
    # Qubit name on a tab above the bar's first task.
    state = _state(run, t)
    tab_color = {"done": DONE, "running": RUNNING, "waiting": WAITING}.get(state, QUEUED)
    labels.append((_x(run.start) + 2, y0 - TAB_H, run.qid, tab_color, WHITE))
    return labels


def _draw_label(draw: ImageDraw.ImageDraw, label: Label) -> None:
    # Text sits on a white plate so it stays readable over the hatch and the playhead.
    tx, ty, text, color, plate = label
    width = draw.textlength(text, font=F_SMALL)
    draw.rectangle((tx - 2, ty - 1, tx + width + 2, ty + 14), fill=plate)
    draw.text((tx, ty), text, font=F_SMALL, fill=color)


def _draw_wait(draw: ImageDraw.ImageDraw, run: Run, top: float, t: float) -> None:
    """Show a MUX that is idle because its next qubit waits for the round."""
    if run.start <= run.ready or t <= run.ready:
        return
    y0 = _bar_top(top, run.lane)
    box = (_x(run.ready) + 1, y0 + 4, _x(min(t, run.start)), y0 + LANE_H - 4)
    draw.rectangle(box, fill=WAITING_BG)
    _hatch(draw, box, WAITING)


def _lane_readout(mode: Mode, lane: int, t: float) -> tuple[str, str, tuple[int, int, int]]:
    """Return the MUX's current activity as (qubit, task or state, color)."""
    runs = [run for run in mode.runs if run.lane == lane]
    for run in runs:
        task = run.task_at(t)
        if task is not None:
            return run.qid, TASKS[task][0], RUNNING
    for run in runs:
        if _state(run, t) == "waiting":
            return run.qid, "waits for round", WAITING
    pending = [run for run in runs if _state(run, t) == "queued"]
    if pending:
        return min(pending, key=lambda r: r.start).qid, "queued", QUEUED
    return "", "all done", DONE


def _status(mode: Mode, t: float) -> str:
    running = sorted(
        ((run, run.task_at(t)) for run in mode.runs if run.task_at(t) is not None),
        key=lambda pair: (-(pair[1] or 0), pair[0].qid),
    )
    waiting = [run.qid for run in mode.runs if _state(run, t) == "waiting"]
    if not running and not waiting:
        if all(_state(run, t) == "done" for run in mode.runs):
            return f"All four qubits done at t = {max(r.end for r in mode.runs):g}"
        return "Not started"
    if waiting:
        others = ", ".join(f"{run.qid}, now on {TASKS[task or 0][0]}," for run, task in running)
        return f"{', '.join(waiting)} waits for round 2: {others} must finish its whole task list"
    names = {run.qid: TASKS[task or 0][0] for run, task in running}
    if mode.name == "parallel_by_mux" and "Q1" in names and "Q8" in names:
        return f"Q1 started when Q0 finished; Q8 is still on {names['Q8']}"
    if len(running) == 2:
        (a, ta), (b, tb) = running
        if ta != tb:
            return (
                f"{a.qid} is on {TASKS[ta or 0][0]} while {b.qid} is on {TASKS[tb or 0][0]}: "
                "no barrier between tasks"
            )
        return f"{a.qid} and {b.qid} both on {TASKS[ta or 0][0]}"
    run, task = running[0]
    return f"{run.qid} runs {TASKS[task or 0][0]}; the other qubits wait their turn"


def render(t: float) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(image)
    draw.text((16, 10), "One-qubit execution modes", font=F_TITLE, fill=INK)
    draw.text(
        (16, 38),
        "MUX0: Q0, Q1    MUX2: Q8, Q9    Both MUXes in the same box stage.",
        font=F_TEXT,
        fill=MUTED,
    )
    draw.text(
        (16, 58),
        "Each qubit runs its own list in order: CheckRabi, then CreateHPIPulse, then CheckT1.",
        font=F_TEXT,
        fill=INK,
    )
    # Time axis.
    axis_y = HEADER - 10
    for tick in range(T_END + 1):
        x = _x(tick)
        draw.line([(x, axis_y), (x, axis_y + 6)], fill=MUTED, width=1)
        if tick % 5 == 0:
            draw.text((x - 4, axis_y - 16), str(tick), font=F_SMALL, fill=MUTED)
    draw.text((16, axis_y - 16), "time (illustrative)", font=F_SMALL, fill=MUTED)

    labels: list[Label] = []
    playhead: list[tuple[float, float]] = []
    for index, mode in enumerate(MODES):
        top = HEADER + index * PANEL
        bottom = top + PANEL - 8
        draw.rectangle((6, top, WIDTH - 6, bottom), outline=GRID, width=1)
        draw.text((16, top + 6), mode.name, font=F_HEAD, fill=INK)
        name_width = draw.textlength(mode.name, font=F_HEAD)
        draw.text((28 + name_width, top + 8), mode.rule, font=F_TEXT, fill=MUTED)
        lanes_top = top + TITLE_H
        lanes_bottom = _bar_top(top, len(LANES) - 1) + LANE_H
        for tick in range(T_END + 1):
            draw.line([(_x(tick), lanes_top), (_x(tick), lanes_bottom)], fill=GRID, width=1)
        for lane, (mux, _) in enumerate(LANES):
            y = _bar_top(top, lane)
            draw.text((16, y - TAB_H + 1), mux, font=F_HEAD, fill=INK)
            qid, activity, color = _lane_readout(mode, lane, t)
            readout = f"{qid} {activity}".strip()
            draw.text((16, y + 9), readout, font=F_SMALL, fill=color)
        for at in mode.barriers:
            x = _x(at)
            y = lanes_top - 2
            while y < lanes_bottom + 4:
                draw.line([(x, y), (x, min(y + 5, lanes_bottom + 4))], fill=INK, width=2)
                y += 9
            draw.text((_x(0) + 2, lanes_bottom + 5), "round 1: Q0, Q8", font=F_SMALL, fill=INK)
            draw.text((x + 6, lanes_bottom + 5), "round 2: Q1, Q9", font=F_SMALL, fill=INK)
        for run in mode.runs:
            _draw_wait(draw, run, top, t)
        for run in mode.runs:
            labels.extend(_draw_run(draw, run, top, t))
        draw.text((16, bottom - 24), _status(mode, t), font=F_TEXT, fill=INK)
        playhead.append((lanes_top, lanes_bottom + 4))

    # Playhead across the lanes of every panel, under the bar labels.
    x = _x(t)
    for y0, y1 in playhead:
        draw.line([(x, y0), (x, y1)], fill=PLAYHEAD, width=2)
    for label in labels:
        _draw_label(draw, label)
    label = f"t = {t:g}"
    width = draw.textlength(label, font=F_SMALL)
    lx = min(max(x - width / 2, X0), X1 - width)
    draw.rectangle((lx - 3, axis_y - 17, lx + width + 3, axis_y - 2), fill=PLAYHEAD)
    draw.text((lx, axis_y - 16), label, font=F_SMALL, fill=WHITE)

    # Legend and caption.
    ly = HEADER + len(MODES) * PANEL + 4
    lx = 16.0
    for short, name in ((short, name) for name, short in TASKS):
        draw.text((lx, ly), short, font=F_TEXT, fill=INK)
        lx += draw.textlength(short, font=F_TEXT)
        text = f" = {name}"
        draw.text((lx, ly), text, font=F_TEXT, fill=MUTED)
        lx += draw.textlength(text, font=F_TEXT) + 26
    ly += 26
    entries = (
        ("not started", QUEUED, "dashed"),
        ("waiting for its round", WAITING, "wait"),
        ("running", RUNNING, "running"),
        ("done", DONE, "done"),
    )
    lx = 16.0
    for text, color, kind in entries:
        box = (lx, ly, lx + 30, ly + 16)
        if kind == "dashed":
            _dashed_rect(draw, box, color)
        elif kind == "wait":
            draw.rectangle(box, fill=WAITING_BG)
            _hatch(draw, box, color)
        elif kind == "running":
            draw.rectangle(box, fill=RUNNING_BG)
            _hatch(draw, box, color)
            draw.rectangle(box, outline=color, width=2)
        else:
            draw.rectangle(box, fill=DONE_BG, outline=color, width=2)
        draw.text((lx + 38, ly + 1), text, font=F_TEXT, fill=INK)
        lx += 38 + draw.textlength(text, font=F_TEXT) + 26
    draw.text(
        (16, ly + 28),
        "Illustrative task list and timing, not a measured benchmark. The scheduler chooses "
        "the actual MUX order and rounds.",
        font=F_SMALL,
        fill=MUTED,
    )
    draw.text(
        (16, ly + 46),
        "A round waits for every qubit's whole task list; it is not a per-task barrier and "
        "does not synchronize pulses.",
        font=F_SMALL,
        fill=MUTED,
    )
    return image


# (time, hold in ms). Pauses sit on the moments that tell the modes apart: Q0 on
# CreateHPIPulse while Q8 is on CheckRabi (1.5), Q1 started or waiting while Q8 is on
# CheckT1 (3.5), round 2 starting (5), and each mode finishing.
# Time of the still poster shown before the editor help plays the GIF: the three modes
# already differ, with Q1 started under parallel_by_mux and waiting under parallel_by_round.
POSTER_T = 3.5
HOLDS = {0.0: 1500, 1.5: 2600, 3.5: 3000, 5.0: 2000, 8.0: 1400, 9.0: 1400, 15.0: 3200}


def timeline() -> list[tuple[float, int]]:
    steps = [round(i * 0.5, 1) for i in range(int(T_END / 0.5) + 1)]
    return [(t, HOLDS.get(t, 240)) for t in steps]


def _check() -> None:
    """Fail fast if the timeline drifts from the totals the docs table states."""
    assert DURATION == {"Q0": 3, "Q1": 4, "Q8": 5, "Q9": 3}, DURATION
    ends = {mode.name: max(run.end for run in mode.runs) for mode in MODES}
    assert ends == {"sequential": 15, "parallel_by_mux": 8, "parallel_by_round": 9}, ends


def build(output: Path, frames_dir: Path | None, ui_dir: Path | None) -> None:
    _check()
    frames = [(render(t), hold) for t, hold in timeline()]
    # One shared palette keeps colors stable between frames and the file small.
    palette_source = frames[len(frames) // 3][0].quantize(
        colors=48, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
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
    if ui_dir is not None:
        ui_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output, ui_dir / output.name)
        poster = render(POSTER_T).quantize(palette=palette_source, dither=Image.Dither.NONE)
        poster.save(ui_dir / f"{output.stem}-poster.png", optimize=True)
    if frames_dir is not None:
        frames_dir.mkdir(parents=True, exist_ok=True)
        for (t, _), (image, _) in zip(timeline(), frames, strict=True):
            image.save(frames_dir / f"t{t:04.1f}.png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--frames", type=Path, default=None, help="Also write PNG frames here")
    parser.add_argument(
        "--ui-dir",
        type=Path,
        default=UI_DIR,
        help="Directory for the editor help copy of the GIF and its poster",
    )
    parser.add_argument("--no-ui", action="store_true", help="Skip the editor help assets")
    args = parser.parse_args()
    build(args.output, args.frames, None if args.no_ui else args.ui_dir)
    print(f"Wrote {args.output} ({args.output.stat().st_size / 1024:.0f} KiB)")


if __name__ == "__main__":
    main()
