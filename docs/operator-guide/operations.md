# Operations

This page covers common operational commands for a local or lab QDash deployment.

## Service Commands

```bash
# Full Docker Compose stack
task deploy-local

# Host-side API/UI with Docker-backed services
task dev-local

# Stop host API/UI and local Docker Compose services
task dev-local-down

# Supporting services only
task dev-services

# Restart the API container in the full Docker stack
task restart-api
```

## Logs

```bash
docker compose logs -f api
docker compose logs -f ui
docker compose logs -f deployment-service
docker compose logs -f user-flow-worker
docker compose logs -f prefect-server
```

The API also writes logs under `logs/api` when mounted by Docker Compose or when run locally.

## Health Checks

- UI reachable: <http://localhost:5714/login>
- API reachable: <http://localhost:5715/docs>
- Prefect reachable: <http://localhost:4200>
- Docker service status: `docker compose ps`

## Common Issues

If the UI cannot reach the API, check `INTERNAL_API_URL` and whether the API is listening on
`API_PORT`.

If workflow execution fails with a missing work pool, restart `deployment-service` and
`user-flow-worker`; the deployment service creates the `user-flows-pool` when registering flows.

If task figures do not render, confirm `CALIB_DATA_PATH` points at the directory mounted to
`/app/calib_data` in Docker.

If Qubex config or task file pages return missing-path errors, confirm `CONFIG_PATH` points
to the Qubex backend configuration tree and `CALIB_TASKS_PATH` points to the calibration
task directory in `.env`.
