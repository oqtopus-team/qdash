QDash can run on Railway as a fake-backend demo by deploying the web UI, API, Prefect, and workflow worker as separate services.

## Service Layout

Create these Railway services in one project:

- `ui`: GitHub repo service using `deploy/railway/ui.toml`.
- `api`: GitHub repo service using `deploy/railway/api.toml`.
- `deployment-service`: GitHub repo service using `deploy/railway/deployment-service.toml`.
- `user-flow-worker`: GitHub repo service using `deploy/railway/user-flow-worker.toml`.
- `prefect-server`: Docker image service from `prefecthq/prefect:3-python3.11`.
- `mongo`: Docker image service from `mongo` with a Railway volume mounted at `/data/db`.
- `postgres`: Railway PostgreSQL service, or a `postgres:14` Docker image service with a volume.

Use Railway private networking for service-to-service traffic. The public domain is only required for `ui`; expose `api` and `prefect-server` only if direct debugging access is needed.

The QDash Railway services use dedicated Dockerfiles under `deploy/railway/`.
They build self-contained images for Railway without changing the repository's
Docker Compose-oriented Dockerfiles.

## GitHub Autodeploy

Set each GitHub-backed service to deploy from the release branch, usually
`main`. Railway deploys linked GitHub services automatically when new commits
are pushed to the connected branch.

For each QDash service, open the Railway service settings and set:

| Service | Branch | Config file |
| --- | --- | --- |
| `ui` | `main` | `/deploy/railway/ui.toml` |
| `api` | `main` | `/deploy/railway/api.toml` |
| `deployment-service` | `main` | `/deploy/railway/deployment-service.toml` |
| `user-flow-worker` | `main` | `/deploy/railway/user-flow-worker.toml` |

Enable autodeploy for each service. If CI checks are required before deploy,
enable Railway's `Wait for CI` setting after the repository has a GitHub
Actions workflow that runs on `push`.

With this setup, merging into `main` triggers Railway deployments for the
services whose watch patterns match the changed files. If a deployment does not
start, check the service's deployment history for skipped deploys and confirm
that the watch patterns include the changed paths.

## Service Commands

The QDash services use the start commands from the config files. For `prefect-server`, set the start command in Railway to:

```sh
prefect server start --host 0.0.0.0
```

Set `PREFECT_API_DATABASE_CONNECTION_URL` on `prefect-server` to the private Postgres connection string:

```sh
postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST:$POSTGRES_PORT/$POSTGRES_DB
```

Railway PostgreSQL commonly provides a `DATABASE_URL`; convert that value to the async SQLAlchemy form above, or define the individual Postgres variables on the service.

## Variables

Use `deploy/railway/fake.env.example` as the starting point for shared variables. Replace passwords before deploying.

Apply the shared fake-backend variables to `api`, `deployment-service`, and `user-flow-worker`:

- `ENV=railway-fake`
- `DEFAULT_BACKEND=fake`
- `PREFECT_API_URL=http://<prefect-private-domain>:4200/api`
- `DEPLOYMENT_SERVICE_URL=http://<deployment-service-private-domain>:<deployment-service-port>`
- `MONGO_HOST=<mongo-private-domain>`
- `MONGO_PORT=27017`
- `MONGO_INITDB_ROOT_USERNAME=<mongo-user>`
- `MONGO_INITDB_ROOT_PASSWORD=<mongo-password>`
- `MONGO_DB_NAME=qdash`
- `CALIB_DATA_PATH=/app/calib_data`
- `CONFIG_PATH=/app/config/qubex-config`
- `QDASH_ADMIN_USERNAME=<admin-user>`
- `QDASH_ADMIN_PASSWORD=<admin-password>`

Apply these variables to `ui`:

- `NEXT_PUBLIC_API_URL=/api`
- `INTERNAL_API_URL=http://<api-private-domain>:<api-port>`
- `NEXT_PUBLIC_PREFECT_URL=https://<prefect-public-domain>` if Prefect is exposed, otherwise leave it unset.
- `NEXT_PUBLIC_COPILOT_ENABLED=false`

For fake execution, no Qubex hardware config repository is required. The Railway
images copy only `config/app`, `config/domain`, and `config/copilot`, then create
an empty `/app/config/qubex-config` so file-browser endpoints have a stable
container path.

## Deployment Order

1. Create `mongo` and `postgres`, then confirm their private connection variables.
2. Create `prefect-server` and wait for `/api/health` or the Prefect UI to respond.
3. Deploy `deployment-service`.
4. Deploy `user-flow-worker`; it creates the `user-flows-pool` work pool and registers system flows on startup.
5. Deploy `api`.
6. Deploy `ui` and assign the public Railway domain.

After login, create or use a fake-backed calibration flow from the UI and confirm that the Prefect run is picked up by `user-flow-worker`.

## Current Limits

This Railway setup is intended for fake-backend demos. Qubex-backed hardware execution still belongs on a host that can reach the lab network and has access to the Qubex configuration repository.
