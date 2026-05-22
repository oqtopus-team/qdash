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

```bash
cp .env.example .env
task deploy-local
```

Use the full stack when you want behavior closest to a Compose deployment.
