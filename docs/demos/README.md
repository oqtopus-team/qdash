# Demo GIFs

Record one UI task with Playwright and convert it to a GIF with ffmpeg.
Published files live in `docs/public/images/guides/`.

## Recording

Start the stack, then record a named scenario in another terminal:

```bash
task dev-local
task docs-gif -- login
```

The recorder uses `UI_PORT` from `.env` and downloads Chromium on its first run.
Intermediate video and poster files stay in `.tmp/docs-demos/<scenario>/`.
Use representative data; recordings can expose whatever appears on screen.

For options, run:

```bash
uv run --with playwright python3 docs/demos/record.py --help
```

## Scenario Format

Copy a scenario in `docs/demos/scenarios/`. Set `name` (the output filename), `target.url`,
and `steps`. `${VAR}` expands from `.env`. The optional `auth` section signs in before recording.
Targets match accessible names or visible text; use `css=` or `xpath=` for explicit selectors.

| Action | Fields | Notes |
| --- | --- | --- |
| `navigate` | `url` (optional) | Defaults to `target.url`. |
| `login` | `whenText` (optional) | Fills credentials from the `auth` env vars. Skipped when pre-authenticated. |
| `click` / `hover` | `target` | Cursor glides to the element first. |
| `fill` | `target`, `value` | Typed character by character. |
| `drag` | `target`, `dx`, `dy` | Grab and pull by a pixel offset. Use for resize handles (`css=[data-separator]`). |
| `press` | `value` | Keyboard key, e.g. `Enter`. |
| `scroll` | `value` | Wheel delta in px. |
| `waitForText` | `text`, `timeoutMs` | Waits until the text is visible. Pick text unique to the target state. |
| `wait` | `value` | Pause in ms. |
| `capture` | `label` | Saves a poster PNG to the run dir. |
| `reload` | – | Reloads the page. |
| `note` | `text` | Logs a note; no UI action. |

`optional: true` lets a step fail without stopping the recording.

## Demo Video

The [Remotion project](./video/README.md) produces the older 30-second demo.
`task docs-video` overwrites the current 72-second published assets with that older version.
The current film uses Fake backend data and an illustrative AI response, disclosed on screen.
Its soundtrack is “Let's Move” (Mixkit item 836), under the
[Mixkit Stock Music Free License](https://mixkit.co/license/#musicFree).

## Generated Diagrams

Regenerate the execution animations from fixed illustrative timelines:

```bash
uv run --no-project --with pillow==13.0.0 python3 docs/demos/one_qubit_execution_modes.py
uv run --no-project --with pillow==13.0.0 python3 docs/demos/two_qubit_cr_schedule.py
```

Both scripts also update GIFs and posters in `ui/public/images/execution-help/`.
Use `--frames DIR` to inspect individual frames or `--no-ui` to skip UI assets.
Do not edit generated copies by hand.

Keep the CR animation fixture aligned with `docs/diagrams/cr-schedule-conflict-graph.svg`.
Check both the schedule and the copied assets:

```bash
uv run --package qdash-workflow --locked pytest tests/qdash/workflow/engine/scheduler/test_cr_schedule_docs_example.py
uv run pytest tests/docs/test_execution_help_assets.py
```
