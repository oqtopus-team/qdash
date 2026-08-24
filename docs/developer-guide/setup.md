# Developer Setup

Use DevContainer for an isolated environment or Nix for a lightweight host shell. The detailed
[Development Environment Setup](../development/setup.md) is the canonical reference for tool
versions, service composition, environment variables, and individual commands.

## DevContainer

```bash
docker compose -f compose.devcontainer.yaml up -d
docker compose -f compose.devcontainer.yaml exec --user vscode devcontainer zsh
```

Inside the container, check Git identity before committing:

```bash
git config --global user.name
git config --global user.email
```

## Nix Host Shell

```bash
nix develop
task dev-local-setup
task dev-local
```

Install dependencies and start the Docker-backed services with host API and UI processes:

```bash
task dev-local-setup
task dev-local
```

Stop them with `task dev-local-down`.

Use the [Operator Setup](../operator-guide/setup.md) when you need the full Compose stack or must
configure Qubex files, persistent storage, authentication, Copilot providers, or remote access.
