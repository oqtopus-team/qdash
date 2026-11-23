# Developer Setup

Use Nix on the host or the DevContainer to get QDash's toolchain. Both use Docker for services.

## Prerequisites

Install Docker with Compose v2.24.4 or later and start the Docker engine. Then clone the repository:

```bash
git clone --branch develop https://github.com/oqtopus-team/qdash.git
cd qdash
```

For a deployed system rather than a development environment, follow [Setup](../user-guide/setup.md).

## Nix Host Shell

Install Nix with `nix-command` and `flakes` enabled, then enter the shell:

```bash
nix develop
```

The shell supplies Python, Bun, Node.js, Task, and the pinned secret scanners. It does not start services.
Continue with [Install Dependencies](#install-dependencies).

## DevContainer

Open the checkout with VS Code's Dev Containers extension, or start it manually:

```bash
.devcontainer/check-shared-repos.sh "$PWD"
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose -f compose.devcontainer.yaml up -d --build
docker compose -f compose.devcontainer.yaml exec --user vscode devcontainer zsh
```

Use `/workspace/qdash` for development. Its host parent is available at `/workspace/repos`.
To share another directory, create it and export its absolute path as `QDASH_SHARED_REPOS_DIR`
before starting the container. The preflight check requires it to exist and be writable.

The checkout is shared; Python dependencies, caches, and UI build output use separate container
volumes. Recreate the container after mount changes. Run development and Git commands as `vscode`;
set Git identity and authenticate inside the container because host credentials are not copied.

For direct Docker Compose commands inside the container, use the host checkout path in
`QDASH_HOST_WORKSPACE`: the Docker daemon resolves bind mounts on the host.

<a id="refresh-dependencies"></a>

## Install Dependencies

Run these from the repository root inside the chosen environment, before checks or generation:

```bash
task dev-local-setup
bun install --frozen-lockfile
lefthook install
```

The first command installs Python and UI dependencies; the second installs the root TypeScript
workspace. VS Code's DevContainer setup installs Python/UI dependencies automatically, but manual
Compose startup does not. Re-running these commands is safe when refreshing dependencies.
Lychee is installed in `~/.local/bin` when needed; keep it on `PATH`.

For documentation work, also run `bun install --cwd docs --frozen-lockfile`, then
`task build-docs`. A successful build ends with `build complete`.

## Run the Development Stack

In this checkout, follow only [Create the Environment File](../user-guide/setup.md#create-the-environment-file)
and [Configure Shared Deployment Settings](../user-guide/setup.md#configure-shared-deployment-settings).
Choose Fake for a first local start and set the administrator password. Skip the operator guide's
clone and production-start commands; start the development stack below instead.
For existing data, keep the MongoDB version that wrote it; follow
[System Updates](../user-guide/system-updates.md) before changing it.

```bash
task dev-local
```

This starts Docker services and hot-reload API/UI processes. Default browser addresses:

| Service | Address |
| --- | --- |
| QDash | `http://localhost:5714` |
| API docs | `http://localhost:5714/api/docs` |
| Prefect, after sign-in | `http://localhost:5714/prefect/` |

When the login page loads, sign in with the administrator credentials from `.env`; API docs should
also load. If either fails, inspect the terminal running `task dev-local` and use
[Operations](../user-guide/operations.md#resolve-common-failures). Keep that terminal running and
make changes in a second terminal with the same Nix or DevContainer environment.

`UI_PORT` changes the browser port. `task dev-local-down` stops the stack.
To start components separately, use `task dev-services`, `task dev-api-local`, and `task dev-ui-local`.
The local API runs metric scripts as local subprocesses.

For two stacks, give each a distinct `ENV`, `UI_PORT`, `API_PORT`, `UI_DEV_PORT`, and published
service ports. Linux host API/UI processes listen on `0.0.0.0`; set `QDASH_DEV_BIND` to restrict
network access. See [development routing](./architecture.md#development-routing) if Caddy returns 502.

## Secret Scanning Tools

Run checks and commits in Nix or the DevContainer so they use the pinned Betterleaks release:

```bash
nix develop -c task check
nix develop -c git commit
```

Inside the DevContainer, omit `nix develop -c`. Never bypass a scanner-version failure.
Follow [Development Flow](./development-flow.md#before-pushing) before pushing.
