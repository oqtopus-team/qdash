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

QDash resolves Qubex files by chip ID. The expected layout is:

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

Confirm that the chip directory exists before starting QDash. Then set the administrator
credentials and common options in
[Configure Shared Deployment Settings](../setup.md#configure-shared-deployment-settings) and
[start QDash](../setup.md#start-qdash).
