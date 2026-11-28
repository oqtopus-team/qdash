# Qubex Backend Setup

Prepare Qubex hardware configuration before starting a lab deployment.

Copy `.env.example.qubex` to `.env` as in [Setup](../setup.md), keep `DEFAULT_BACKEND=qubex`,
and set `CONFIG_PATH` to the configuration root.

## Place the Qubex Configuration

Use one directory and one Qubex system per chip. Its system ID must equal the chip ID:

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

The `chip.yaml`, `system.yaml`, and `wiring.yaml` entries use that ID. `skew.yaml` is needed
when the hardware requires inter-box timing adjustments. Follow the
[Qubex configuration guide](https://amachino.github.io/qubex/user-guide/getting-started/system-configuration/)
for file contents. Separate hardware systems driving one physical chip need separate QDash
deployments and chip directories.

## Create the Configuration of a New Chip

1. Open **Chip → Create Chip** and enter an ID using letters, digits, periods, hyphens, or
   underscores, starting with a letter or digit.
2. Under **Qubex configuration**, choose **Copy from** an existing system or **Start from template**
   with backend `quel1` or `quel3`.
3. Create the chip, then open **Config** to complete or correct the hardware settings.
4. Check wiring, boxes, device parameters, and frequency defaults before running **Box Setup**.

Templates contain empty wiring and box maps with examples; they are not ready to run.
Copying reuses hardware files, not measured parameter values. Existing chip directories remain
unchanged. Without configuration creation or a mounted tree, only the chip record is created.

To edit the generated files on **Config**:

1. Select the chip's file in the file tree, then select **Edit** to unlock the editor.
2. Make the change and select **Save** (or Cmd/Ctrl+S).
3. Check the saved changes before running hardware. When using a configuration repository,
   select **Create PR** and follow its link to review and merge the changes.

**Save** changes local files only. **Pull** resets them to the repository's `main` branch and removes
untracked files, including saved local work. Before pulling, merge your **Create PR** changes or
copy them outside the deployment's configuration directory.

### Register an Existing Configuration

When a chip directory already exists under `CONFIG_PATH`, register it in QDash without creating
new files:

1. Open **Chip → Create Chip** and select **Use existing config**.
2. Under **Existing configuration**, choose the system. Its system ID becomes the chip ID.
   Systems already registered in the project are marked **(already registered)** and cannot be
   chosen.
3. Check the **Topology Template**. QDash preselects a matching template when available
   (4 qubits per MUX); verify the qubit count and layout before continuing.
4. Select **Create Chip**.

QDash creates only the chip record and uses the existing directory as is, without copying or
modifying its files. **Use existing config** appears only when the mounted configuration tree
contains at least one system.

## Check Parallel Execution on QuEL-3

QDash's checks do not establish the parallel capacity of your hardware. With `<box ID>:<port>`
wiring, including the QuEL-1 and QuEL-3 templates:

| Operation | Checks | Does not establish |
| --- | --- | --- |
| One-qubit parallel modes | One qubit per MUX at a time | Independence of MUXes sharing a box |
| Two-qubit CR grouping | Shared MUXes and readout/control modules | Cross-role, read-in, pump, or finer port conflicts |
| Hardware reservation | Conflicts between executions | Safety of parallel groups within a run |

Until verified on the deployment, use `execution_mode="sequential"` for one-qubit steps and
set two-qubit `max_parallel_ops` to a supported value (1 for one pair at a time).
Renaming modules does not make the scheduler match unmodeled hardware. Experimental simultaneous
spectroscopy needs explicit task and backend support.

## Use a Configuration Repository

Set these optional `.env` values for configuration synchronization:

```dotenv
CONFIG_REPO_URL=https://github.com/<owner>/<qubex-config-repo>.git
GITHUB_USER=<github-username>
GITHUB_TOKEN=<github-token>
```

Sessions can pull configuration before runs; enabled workflow pushes can version updated notes
and parameters afterward. Confirm existing chip directories, then continue
[shared deployment settings](../setup.md#configure-shared-deployment-settings).
