# Docs demo GIFs

Playwright records YAML scenarios against the real UI; ffmpeg converts them to GIFs under
`docs/public/images/guides/`. Guide pages reference `/images/guides/<name>.gif`.

## Recording

Start the local stack first (the recorder talks to the UI on `UI_PORT` from
`.env`):

```bash
task dev-local
```

Then record a scenario by name:

```bash
task docs-gif -- login
```

Or run the recorder directly for more control:

```bash
uv run --with playwright python3 docs/demos/record.py \
  --scenario docs/demos/scenarios/login.yaml --fps 13 --gif-width 900
```

The first run downloads Chromium into `~/.cache/ms-playwright`. The webm and
poster frames are kept under `.tmp/docs-demos/<scenario>/`; the final GIF lands
in `docs/public/images/guides/`.

Useful flags: `--fps` / `--gif-width` (size vs smoothness), `--pause` /
`--type-delay` / `--slowmo` (pacing), `--viewport 1440x900 --scale 2` (crisper,
larger files), `--headed` (watch the browser), `--include-login` (record the
login flow instead of pre-authenticating).

## Scenario format

```yaml
name: login                       # also the output GIF name
description: ...
target:
  url: "http://localhost:${UI_PORT}/login"   # ${VAR} expands from .env
  viewport: "1280x800"
auth:                             # optional; when present, login happens
  envFile: ".env"                 # BEFORE recording so the video starts clean
  usernameEnv: QDASH_ADMIN_USERNAME
  passwordEnv: QDASH_ADMIN_PASSWORD
  loginPath: "/login"
steps:
  - action: navigate
  - action: click
    target: "Split view"          # ARIA role+name (matches title/aria-label) or visible text
  - action: fill
    target: "Enter your user ID"
    value: "${QDASH_ADMIN_USERNAME}"
  - action: drag
    target: "css=[data-separator]"  # explicit selector via css=/xpath=
    dx: -260
    dy: 0
  - action: capture
    label: "01-state"             # saves a poster PNG (the video records motion)
```

### Step actions

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

Add `optional: true` to a step to continue if it fails.

Targets resolve by ARIA role + accessible name first (so `title` / `aria-label`
on icon-only buttons work), then by visible text. Prefix with `css=` or `xpath=`
for an explicit selector.

## Demo video

`video/` holds the Remotion project for the previous 30-second product demo. The current
README and docs assets come from the full film in the
[qdash-film repository](https://github.com/orangekame3/qdash-film), merged in
[PR #4](https://github.com/orangekame3/qdash-film/pull/4) at
`b5eb360447d1338396d540454ffd14bdce6f9c3a`. The published
`docs/public/images/qdash-demo.gif` and `docs/public/videos/qdash-demo.mp4` are
byte-identical copies of `media/qdash-film.gif` and `media/qdash-film.mp4` at that
revision: both are the full 72-second film. The UI uses QDash fake-backend data;
the AI Chat response is illustrative and redrawn, as disclosed on screen. See the
film’s [asset provenance and licence notes](https://github.com/orangekame3/qdash-film/blob/b5eb360447d1338396d540454ffd14bdce6f9c3a/ASSETS.md).
Running `task docs-video`
regenerates the previous demo and overwrites the current published assets. See
`video/README.md` for the previous demo's source and editing instructions.

## Generated diagrams

`one_qubit_execution_modes.py` draws
`docs/public/images/guides/one-qubit-execution-modes.gif`, the comparison of the
one-qubit execution modes that splits each qubit's bar into its tasks, from a
fixed illustrative timeline with Pillow and the font bundled with it, so the
output does not depend on the local UI or fonts. Edit the timeline or labels in the script, then regenerate:

```bash
uv run --no-project --with pillow==13.0.0 python3 docs/demos/one_qubit_execution_modes.py
```

Add `--frames .tmp/execution-modes` to write every frame as a PNG for review.

`two_qubit_cr_schedule.py` draws `docs/public/images/guides/two-qubit-cr-schedule.gif`, the
execution of a two-qubit CR schedule with `max_parallel_ops = 4`, the same way. Its fixture
(wiring, pairs, groups, and graph colors) is also drawn by
`docs/diagrams/cr-schedule-conflict-graph.svg` and checked against the scheduler by
`tests/qdash/workflow/engine/scheduler/test_cr_schedule_docs_example.py`. Both drawings color
pairs by execution group with the same four colors (`GROUP_COLOR` in the script) and write
conflict-graph colors as text. Change the three together, then regenerate and run the test:

```bash
uv run --no-project --with pillow==13.0.0 python3 docs/demos/two_qubit_cr_schedule.py
uv run --package qdash-workflow --locked pytest tests/qdash/workflow/engine/scheduler/test_cr_schedule_docs_example.py
```

`--frames DIR` works here too.

Both scripts also write the workflow editor's **Execution help** media to
`ui/public/images/execution-help/`: a byte-identical copy of the GIF and a still poster PNG drawn
from the same timeline at `POSTER_T`. Do not edit those files by hand; regenerate them with the
scripts above, or pass `--no-ui` to skip them. `tests/docs/test_execution_help_assets.py` fails
when a UI copy differs from its docs GIF:

```bash
uv run pytest tests/docs/test_execution_help_assets.py
```
