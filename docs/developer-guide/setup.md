# Developer Setup

Use DevContainer when you want the most isolated environment. Use Nix when you want a lightweight
host shell with the project toolchain.

## DevContainer

```bash
docker compose -f compose.devcontainer.yaml up -d --build
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

`task dev-local` starts Docker-backed services and runs the API/UI on the host.

## Full Docker Stack

Create and review `.env` before starting the stack:

```bash
cp .env.example.qubex .env
```

Edit `.env` if you need custom ports, data paths, admin credentials, Qubex config repository
settings, remote access settings, or Copilot provider credentials. For Qubex workflows, make sure
`CONFIG_PATH` contains the chip configuration tree described in the
[Operator Setup](../operator-guide/setup.md#qubex-configuration-files).

Then start the full stack:

```bash
task deploy-local
```

Use the full stack when you want behavior closest to a Compose deployment.
