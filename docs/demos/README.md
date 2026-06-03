# Docs demo GIFs

Animated GIFs for the user guide are recorded from declarative YAML scenarios by
driving the real UI with Playwright, then converting the recording to a GIF with
ffmpeg. Scenarios and the recorder live here; the GIFs are written to
`docs/public/images/guides/` and referenced from guide pages as
`/images/guides/<name>.gif`.

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
