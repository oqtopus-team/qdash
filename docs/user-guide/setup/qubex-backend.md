# Qubex Backend Setup

Use the Qubex backend for a lab deployment that runs QDash calibration tasks against supported
quantum-control hardware.

Complete [Prepare the Host](../setup.md#prepare-the-host), then create `.env` from the Qubex
example:

```bash
cp .env.example.qubex .env
```

Review these backend-specific settings before starting services:

| Variable | Purpose |
| --- | --- |
| `ENV` | Deployment label; the example uses `dev-qubex` |
| `DEFAULT_BACKEND` | Keep `qubex` |
| `CONFIG_PATH` | Root of the Qubex configuration tree |
| `CONFIG_REPO_URL` | Optional Git repository that owns the configuration tree |
| `GITHUB_USER` / `GITHUB_TOKEN` | Optional credentials for configuration pull and push |
| `QUBEX_CONFIGURATION_MODE` | Optional Qubex experiment configuration mode |
| `QUBEX_LAYOUT` | Optional `shared` or `legacy` to override configuration layout detection |

## Place the Qubex Configuration

Prepare the hardware and parameter files described in the
[Qubex system configuration guide](https://amachino.github.io/qubex/user-guide/getting-started/system-configuration/)
and place them under `CONFIG_PATH`.

QDash reads two layouts and detects which one is in use. The shared layout is the Qubex 1.5
recommendation: one set of hardware files for every chip, and one parameter directory per
System. A System is the set of control boxes that drives a chip, named by its `system_id` in
`system.yaml`; a chip driven by one System uses the chip ID as its System ID.

```text
config/qubex-config/            # shared layout
  config/
    chip.yaml
    system.yaml
    wiring.yaml
    box.yaml
    skew.yaml
  params/
    <system_id>/
      measurement_defaults.yaml
      ...
  calibration/
    <system_id>/
      calib_note.json
```

The legacy layout keeps a copy of every file under the chip directory:

```text
config/qubex-config/            # legacy layout
  <chip_id>/
    config/
      chip.yaml
      box.yaml
      system.yaml
      wiring.yaml
      skew.yaml
    params/
    calibration/
```

QDash reads the layout version from `<CONFIG_PATH>/qubex-config.json`: `"layout_version": "2.0"`
is the shared layout and `"1.0"` the legacy one (see [qubex-config Layout](../../reference/qubex-config-layout.md)).
The qubex-config repository is expected to carry that file. A tree without it is read as shared
when `<CONFIG_PATH>/config/chip.yaml` exists and legacy otherwise, and the **Config** page shows a
**no manifest** warning until the file is added. Set `QUBEX_LAYOUT=shared` or
`QUBEX_LAYOUT=legacy` to override both. The Config page shows the detected layout and version
next to the repository mode.

The example sets `CONFIG_PATH=./config/qubex-config`. In the legacy layout a task for
`chip_id="64Qv3"` reads shared files from `./config/qubex-config/64Qv3/config` and parameters
from `./config/qubex-config/64Qv3/params`; in the shared layout it reads
`./config/qubex-config/config` and `./config/qubex-config/params/64Qv3`. `skew.yaml` is needed
only when the Qubex setup requires inter-box timing adjustment.

When `system.yaml` lists several Systems for one chip, each calibration session runs on the
System that wires the targeted qubits. A run whose qubits span two Systems is refused, and a
coupling whose qubits sit on different Systems cannot be calibrated. Execution records keep the
System in the execution note (`system_ids`) and on every task result (`system_id`).
How this works: [Chips and Systems](../../developer-guide/architecture/qubex-systems.md).

To convert an existing legacy tree, run `scripts/convert_layout.py` from the qubex-config
repository against a copy of the tree; it merges the per-chip hardware files into `config/`, moves
each chip's `params` and `calibration` directories under their System ID, and `--verify` checks
with the Qubex `ConfigLoader` that every System reads the same qubits, boxes and wiring as before.

## Use a Configuration Repository

QDash keeps the configuration tree under `CONFIG_PATH` in sync with a Git repository when the
repository values are set:

```dotenv
CONFIG_REPO_URL=https://github.com/<owner>/<qubex-config-repo>.git
GITHUB_USER=<github-username>
GITHUB_TOKEN=<github-token>
```

The values select one of three synchronization modes. The **Config** page shows the active mode
(**GitHub**, **Local git**, or **No repository**), the layout, a **review** badge when pull
requests are required, and the number of unpublished changes next to the repository menu.

| Mode | When | Behaviour |
| --- | --- | --- |
| `github` | All three values are set | `CONFIG_PATH` is the clone of the repository. A calibration session pulls before it starts and publishes its parameter files and calibration note when it finishes. A manual parameter edit is published at once |
| `local-git` | `CONFIG_PATH` holds a `.git` directory but a value is missing | Every publish becomes a local commit; nothing is pulled or pushed |
| `plain` | No `.git` directory and no values | Files are written in place; there is no history beyond the files themselves |

Publishing never resets the working tree, so parameter values another session wrote but has not
published yet stay in place. A pull first publishes unpublished parameter and calibration-note
files, then moves the tree to the remote branch. A pull is refused while the shared hardware files
(`config/*.yaml`) hold unpublished edits: the **Config** page then asks whether to discard them.
Choose **Create PR** first to keep them, or **Discard and pull** to drop them.

Set `github.review_required: true` in `config/app/workflow.yaml` to make sessions open a pull
request for their files instead of pushing to the branch directly. Until that pull request merges,
a session that edits the same files locally cannot pull, so enable it only when someone reviews
the proposals promptly. The **Config** page's **Create PR** always opens a pull request holding
only the files that changed. **Sync** in its repository menu publishes unpublished calibration
files and pulls, the same as `POST /config/repository/sync`; it is absent without a repository.

Confirm that the chip directory exists before starting QDash. Then set the administrator
credentials and common options in
[Configure Shared Deployment Settings](../setup.md#configure-shared-deployment-settings) and
[start QDash](../setup.md#start-qdash).
