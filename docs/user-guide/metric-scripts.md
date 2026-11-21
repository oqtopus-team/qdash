# Metric Scripts

A metric script is a short Python file that computes one value per qubit or per directed qubit
pair from your calibration data, such as the median ZX90 fidelity of each coupling over the
last two weeks. QDash runs it on the server and shows the result in a metric panel on a
[dashboard](./dashboards.md), as a chip map or a table.

## Create a Script

Project editors and owners can create and edit scripts; every member can open a script shared
with the project and preview its saved version.

1. Open **Dashboards**, select the **Scripts** tab, and select **New script**.
2. Enter a name and an optional description.
3. Under **Start from**, choose **Blank script** or a template: **Getting started**,
   **Frequency collision checks**, or **Median ZX90 fidelity** (see
   [Templates](#templates)). The script gets a copy of the template.
4. Choose **Private** or **Shared with project**, then create the script. The script editor
   opens.

The editor shows the code on the left. On the right, **Settings** holds the name,
description and visibility, **Diagnostics** lists problems with their line numbers (select one
to jump to the line), and **Preview** shows the result on a chip. On a narrow screen, the
**Code** and **Settings & preview** tabs switch between the two sides without losing unsaved
changes.

- **Validate** checks the code without saving it.
- **Preview** runs one metric of the code in the editor, saved or not, on the chip and period
  you choose. Nothing is saved.
- **Save** (Cmd/Ctrl+S) stores the code as a new revision.

A member who cannot edit the script previews its saved version and can select **Copy to my
scripts** to get a private copy to change.

## Write a Metric

A metric is a function decorated with `@metric`. QDash calls it once for every qubit of the chip
and shows what it returns:

```python
from qdash_metrics import metric


@metric(title="T2 echo / T1", unit="dimensionless")
def coherence_ratio(target, ctx):
    t2 = ctx.data["t2_echo"][target].latest()
    t1 = ctx.data["t1"][target].latest()
    return t2 / t1
```

`target` is the qubit number as a string (`"12"`), and `ctx` gives access to the data, the chip
layout and the panel's parameters. Output from `print()` appears under **Script output** in the
preview.

| Setting | Meaning |
| --- | --- |
| `title` | The name panels and pickers show; it cannot be empty. |
| `unit` | The unit of the value, such as `MHz`, `us`, `%`, or `dimensionless` for a ratio. |
| Function name | The metric's identifier inside the script. Renaming the function makes it a different metric, and panels that showed the old one must be pointed at the new one. |
| `target` | `"qubit"` (the default) or `"pair"` for a metric per directed qubit pair. |
| `hops` | For pairs: `(1,)` for neighbouring qubits only, `(2,)` for qubits two steps apart, `(1, 2)` for both (the default). |
| `parameters` | Values a panel can adjust; see [Parameters, Colours and Legends](#parameters-colours-and-legends). |
| `legend` | A legend that explains the colours. |

A function can return a number in the declared unit, a value with a unit, `None`, or a
`CellResult`. `None` leaves the target deliberately empty. A non-finite number, a value whose
unit cannot be converted to the declared one, or an exception marks that one target as an
error with the line it occurred on; the other targets are still evaluated.

A script can define several metrics: decorate each function you want to show, and keep helper
functions without the decorator. Each metric appears separately under the script's name in the
panel editor's **Show** list and in the preview's metric picker.

## Read Data

`ctx.data["metric name"][target]` reads one metric of one target. The metric names are the keys
QDash uses for chip metrics, such as `t1`, `t2_echo`, `qubit_frequency`, or
`zx90_gate_fidelity`; an unknown name fails every target with a message listing where the names
come from.

`.latest()` returns the most recent completed, non-excluded value **within the panel's
period**. It does not fall back to an older value: when the period holds none, the target is
shown as missing. This is the latest measurement, not necessarily the value currently used for
operation.

`.history()` returns every measurement in the period, oldest first. Each item has `value`,
`timestamp` (UTC), `task_id`, `execution_id`, and `excluded`. Each item is one task result, so a
median or mean over `history()` is a statistic of the raw observations. Results excluded from
statistics are left out unless you pass `include_excluded=True`. To read a different window,
pass `start` and `end` with a timezone, for example `start="2026-11-01T00:00:00+09:00"`.

### Units

Values carry their unit. QDash applies the unit and scale configured for the metric once, so a
fidelity stored as `0.99` reads as `99 %`; do not multiply by the scale again. Convert with
`.to("MHz")` or `.to("percent")` and take `.magnitude` for a plain number. Values in compatible
units can be added and subtracted directly, and a plain number you return is read in the
declared `unit`.

### Pairs Are Directed

A pair metric runs once for each direction: `0>1` and `1>0` are separate targets. The `target`
argument is a pair with `source`, `target` and `hops`. `ctx.data["zx90_gate_fidelity"][pair]`
reads the coupling in exactly that direction; a coupling measured only as `1-0` is missing for
`0>1`. To read a qubit metric for a pair, index with `pair.source` or `pair.target`.
`ctx.coupling_strength(a, b)` is the one lookup that tries both directions.

### Chip Layout

`ctx.topology.neighbors(qubit)` lists the coupled qubits. `ctx.topology.offset(qubit, row=-1)`
returns the qubit one row up on the chip layout, or `None` at the edge. Both can reach qubits
outside what a panel shows. The chip needs a topology; without one, previews and panels report
that the chip has no topology.

## Show Counts and Missing Data

Wrap the value in `CellResult` to add details that appear when someone selects the target:

```python
import statistics

from qdash_metrics import CellResult, metric


@metric(title="Median dispersive shift", unit="MHz")
def median_shift(target, ctx):
    values = [point.value.to("MHz").magnitude
              for point in ctx.data["dispersive_shift"][target].history()]
    if len(values) < 3:
        return CellResult(None, assessment={"label": "fewer than 3 observations",
                                            "count": len(values)})
    return CellResult(statistics.median(values),
                      assessment={"label": f"median of {len(values)}",
                                  "count": len(values),
                                  "checks": [("min", min(values)), ("max", max(values))]})
```

`count` appears in the table's **Count** column and the details, `label` next to the value,
`checks` under **Checks**, and `estimates` (a list of sentences) under **Defaults and
estimates**. Returning `CellResult(None, assessment=...)` shows the target as missing together
with the reason. Report a count for every aggregate, so a median of one observation does not
look like a median of fifty.

## Parameters, Colours and Legends

A `Parameter` is a value each panel can change, such as a threshold:

```python
from qdash_metrics import CellResult, Legend, Parameter, metric


def ratio_legend(ctx):
    boundary = ctx.params["boundary"]
    return Legend.categorical([("#2563eb", f"below {boundary:g}"),
                               ("#dc2626", f"{boundary:g} or above")])


@metric(title="T2 echo / T1 against a boundary", unit="dimensionless",
        parameters={"boundary": Parameter(default=1.0, label="Boundary", min=0)},
        legend=ratio_legend)
def ratio_flag(target, ctx):
    ratio = ctx.data["t2_echo"][target].latest() / ctx.data["t1"][target].latest()
    value = float(ratio.to("dimensionless").magnitude)
    return CellResult(value, color="#2563eb" if value < ctx.params["boundary"] else "#dc2626")
```

The type of `default` sets the input: `1` an integer, `1.0` a number, `True` an on/off switch,
and a string with `choices=["a", "b"]` a choice. `min` and `max` bound numbers; `step` is the
input step; `unit` is a label only and does not convert values. Every parameter needs a valid
default. A panel that sets an invalid value cannot be saved.

`CellResult(value, color="#RRGGBB")` colours one target. `Legend.categorical([(colour,
label), ...])` explains your colours but does not assign them. `Legend.continuous([(value,
colour), ...])` is a colour scale, in the metric's declared unit, with at least two increasing
stops; QDash colours each target along it. Without either, QDash picks a scale over the values.

## Periods

The panel or the preview sets the period, not the script. **Last days** covers the given number
of days up to the moment the metric runs, so a saved panel always shows the most recent days.
**Fixed range** always covers the same start and end. `ctx.start` and `ctx.end` hold the period
in UTC, and the preview and the panel footer show the period that was used.

## Save and the Active Revision

Each **Save** creates a revision, **r1**, **r2**, and so on. QDash checks the code on save:

- When it validates, the new revision becomes the *active* revision.
- When it does not, the code and its diagnostics are saved, the script is marked invalid, and
  the previous valid revision stays active. Nothing that uses the script breaks while you fix it.
- A script without any valid revision shows **No valid revision** and cannot be added to a
  panel.

Dashboard panels stay on the revision they were added with until an editor updates them; see
[Keep Panels on a Known Script Revision](./dashboards.md#keep-panels-on-a-known-script-revision).
When someone else saved the script while you were editing it, QDash keeps your draft and offers
**Load saved version**; saving again replaces their revision.

Validation only loads the code and its `@metric` declarations. Mistakes inside a metric function,
such as a misspelled metric name, appear when you preview it.

## Limits

Scripts may import only `numpy`, `scipy`, `math`, `statistics`, and `qdash_metrics`. Reading
files, running other programs, `exec`, `eval`, and network access are not available; all data
comes from `ctx`. One run stops after 60 seconds and has a memory limit by default (an
administrator can change both; see [Limit Metric Script Runs](./setup.md#limit-metric-script-runs)),
`print()` output is kept up to 16 KiB, and a script can be up to 256 KiB.

A single `history()` read covers at most 400 days and 5,000 measurements, and one run makes at
most 2,000 data reads. A longer span is cut to its most recent 400 days and the preview says so;
exceeding a count marks the affected targets as errors naming the limit. Narrow the period, or
read each metric once and reuse it. When several people preview at the same time, a run can be
refused because the queue is full; try again a moment later. When the container that runs
scripts is down, validation, saving and previews report that the metric script runner is not
available and nothing is saved; ask an administrator.

These limits protect the server from mistakes in trusted project members' code; they are not a
security boundary for untrusted code.

## Templates

| Template | What it shows | Parameters |
| --- | --- | --- |
| **Getting started** | T2 echo / T1 per qubit, the frequency gap to the qubit one row up, and the mean dispersive shift over the period with its count | None |
| **Median ZX90 fidelity** | The median of every ZX90 gate fidelity measurement of each directed coupling in the period, with the number of observations; couplings with too few observations are grey | **Minimum observations** (default 3) |
| **Frequency collision checks** | The qubex-compatible frequency-collision checks Type0A to Type9 and Type2C, as coloured qubits and directed edges with the terms behind each verdict | Frequency window, detuning, coherence limits, CNOT time, fallback values |

The **Frequency Collision Map** dashboard template uses the collision script. The values are the
ratio of each estimate to its limit: blue below one, orange on the boundary, red above. Type2C
instead shows a two-photon detuning in MHz and turns red inside its window, which is a screening
aid rather than a calibrated tolerance.

### Median ZX90 Fidelity per Coupling

1. On **Scripts**, select **New script**, choose **Median ZX90 fidelity**, and create it.
2. Under **Preview**, choose the chip, the metric **Median ZX90 gate fidelity**, **Last days**
   with 14, and **Map**. Select **Preview**.
3. Each edge shows the median of that direction's measurements. Select an edge to see the number
   of samples, the minimum, the maximum, and the time of the latest measurement. Grey edges have
   fewer measurements than **Minimum observations**; lower it under **Parameters** to include
   them.
4. Select **Save**, then on a dashboard select **Add panel** and choose **Median ZX90 gate
   fidelity** under the script's name in **Show**. Set **Last days** to 14, choose **Map** or
   **Table**, and **Apply**.

## Write a Script with the Agent

Ask the [Agent](./ai-chat.md) for the analysis you want, for example "show the median ZX90
fidelity over the last 14 days per coupling" or "add a minimum sample count to this script". It
reads the available metric names and the templates, writes the script, validates it, previews
it on your chip, and shows you the code and a summary of the result. Saving a script or a
dashboard asks for your approval first.

When the script is open in the script editor, the Agent sees the code in the editor, including
unsaved changes. It proposes a change as a diff in the chat; select **Apply to editor** to put it
in the editor, check it with **Validate** and **Preview**, and **Save** when you are satisfied.
The Agent does not save over your draft unless you ask it to.

How this works: [Metric Scripts architecture](../developer-guide/architecture/metric-scripts.md).
