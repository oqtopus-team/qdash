# QDash Tools

Run these scripts from the repository root with `uv run python src/tools/<script>.py`.
Use `--help` on the CLI tools below for options.

| Script | Purpose |
| --- | --- |
| `cr_scheduler_visualizer.py` | Plot CR schedules and group conflicts |
| `cr_schedule_generator.py` | Generate legacy CR schedules |
| `get_latest_task_results.py` | Fetch task results and download figures |
| `device_topology_generator.py` | Generate topology configuration |
| `get_two_qubit_pair.py` | Extract coupling pairs |
| `read_wiring.py` | Read wiring configuration |
| `greedy.py` | Graph coloring helpers |
| `diagnose.py` | Diagnostics |
| `converter.py` | Data conversion |

## Plot a Schedule

```bash
uv run python src/tools/cr_scheduler_visualizer.py --chip-id 64Qv3 --use-plugins
```

Results go to a timestamped directory under `.tmp/`.

## Read Task Results

Set `QDASH_API_TOKEN`, then specify the deployment's API URL:

```bash
uv run python src/tools/get_latest_task_results.py   --base-url http://localhost:5714/api --chip-id 64Qv3 --task CheckRabi
```

Add `--download-figures ./figures` to save Plotly JSON files, or `--output json` for raw results.
Cloudflare-protected deployments also need the script's `CF_ACCESS_CLIENT_ID` and
`CF_ACCESS_CLIENT_SECRET` settings.
