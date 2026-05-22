# Workflow Operations

QDash uses Prefect for workflow orchestration. Three services are involved in normal workflow
execution.

| Service | Role |
| --- | --- |
| `prefect-server` | Stores flow runs, deployments, schedules, and execution state |
| `deployment-service` | Registers user flow files as Prefect deployments |
| `user-flow-worker` | Polls the Prefect work pool and executes user flows |

## User Flow Registration

When a user saves or runs a workflow, the API writes the flow file under the project user-flow
directory, then asks `deployment-service` to register the Prefect deployment. The deployment
service ensures the `user-flows-pool` work pool exists.

## Execution Artifacts

Calibration results and figures are written under `CALIB_DATA_PATH`. In Docker this path is
mounted to `/app/calib_data`; host-side API runs resolve stored container paths back to the local
mount.

## Schedules

Schedules are managed through the API and deployment service. Use the Prefect UI for inspection,
but prefer QDash APIs/UI for changes so project metadata stays consistent.
