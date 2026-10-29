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

## Place the Qubex Configuration

Prepare the hardware and parameter files described in the
[Qubex system configuration guide](https://amachino.github.io/qubex/user-guide/getting-started/system-configuration/)
and place them under `CONFIG_PATH`.

QDash resolves Qubex files by chip ID and runs every chip with `system_id` equal to its chip ID:
one chip directory holds exactly one Qubex system, and the `chip.yaml`, `system.yaml`, and
`wiring.yaml` entries in it are all keyed by that ID. The expected layout is:

```text
config/qubex-config/
  <chip_id>/
    config/
      chip.yaml
      box.yaml
      system.yaml
      wiring.yaml
      skew.yaml
    params/
      measurement_defaults.yaml
      ...
    calibration/
      calib_note.json
```

The example sets `CONFIG_PATH=./config/qubex-config`. A task for `chip_id="64Qv3"` therefore reads
shared files from `./config/qubex-config/64Qv3/config` and parameters from
`./config/qubex-config/64Qv3/params`. `skew.yaml` is needed only when the Qubex setup requires
inter-box timing adjustment.

When one physical chip is driven by two systems, for example quel1 and quel3 hardware that cannot
share one Qubex system, run a separate QDash deployment for each system. Each deployment registers
its own chip ID and directory, such as `144Qv3` and `144Qv3-quel3`, and both can point at the same
configuration repository.

## Create the Configuration of a New Chip

Creating a chip from **Chip** > **Create Chip** also creates its directory, `<chip_id>/`, under
`CONFIG_PATH` with `system_id` equal to the chip ID. The **Qubex configuration** section of the
dialog sets what goes into it:

| Setting | Result |
| --- | --- |
| **Wiring**: **Copy from** an existing system | `wiring.yaml` gets that system's rows under the new chip ID. `box.yaml`, `skew.yaml`, and the other hardware files are copied unchanged, and `system.yaml` takes the source's backend and settings. |
| **Wiring**: **Start from template** | `system.yaml`, `wiring.yaml`, and `box.yaml` include commented examples for the selected **Backend** (`quel1` or `quel3`). |
| Checkbox cleared | Only the chip record is created. |

Use **Start from template** when there is no source configuration or the hardware setup changes.
Open **Config** after creation, fill in the backend connection settings in `system.yaml`,
and replace the empty wiring list and box map with entries based on the commented examples.
Uncomment and adapt the examples to your hardware before running calibration.
The chip ID and qubit count are filled in automatically.
For `quel1`, QDash also creates `skew.yaml` with commented examples for inter-box timing
adjustment. Fill in the box timing values and measurement ports when your setup requires
synchronization. The `quel3` template does not create this file.

The **Copy from** list shows directories under `CONFIG_PATH` that have `config/wiring.yaml`.
It skips directories with invalid chip IDs (including hidden directories), the reserved
`template`, `archive`, `schemas`, and `scripts`
directories, and sources whose wiring or system configuration cannot be read or names a
different system. Missing `system.yaml` or `chip.yaml` files do not exclude a source;
without a backend setting, QDash uses `quel1`. Use **Copy from** when the new chip goes onto
wiring that an existing chip already uses, for example a chip replaced in the same cryostat.

For chip registration, the chip ID must start with a letter or digit and contain only
letters, digits, periods, hyphens, and underscores. Reserved directory names are not allowed,
even when configuration creation is disabled or no configuration tree is mounted.

If checking the configuration tree fails, the dialog shows an error and blocks creation.
Close and reopen the dialog to retry.

Parameter files in `params/` start from QDash's templates for the backend; values are never
copied from the source system. Most files have empty `data`. `readout_frequency.yaml` and
`control_frequency.yaml` list every qubit with a null value so Qubex can activate it for initial
setup. Their defaults use the connected readout box's frequency band, or the backend's band when
the box is not yet configured. If you change the box or wiring after creating the chip, update
these frequency defaults to match the configured band before running Box Setup.
`calibration/calib_note.json` starts as `{}`. When `<chip_id>/` already exists, QDash keeps it
unchanged and creates only the chip record. Without a mounted configuration tree, the dialog
creates only the chip record.

The new files exist only in the local tree until you open **Config** and select **Create PR**.
Edit the copied wiring and boxes there when the new chip does not use every MUX of the source.

## Use a Configuration Repository

Set the repository values when the Qubex configuration tree is managed in Git:

```dotenv
CONFIG_REPO_URL=https://github.com/<owner>/<qubex-config-repo>.git
GITHUB_USER=<github-username>
GITHUB_TOKEN=<github-token>
```

With these values, calibration sessions can pull the latest configuration before running. The
file management UI can also pull or push the repository. When workflow push is enabled, QDash can
commit updated calibration notes and parameter YAML files after a run.

Confirm that each existing chip has its directory before starting QDash; new chips get theirs
when you [create them](#create-the-configuration-of-a-new-chip). Then set the administrator
credentials and common options in
[Configure Shared Deployment Settings](../setup.md#configure-shared-deployment-settings) and
[start QDash](../setup.md#start-qdash).
