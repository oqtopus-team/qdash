#!/usr/bin/env bash
set -euo pipefail

sudo mkdir -p \
  "${HOME}/.codex" \
  "${HOME}/.local" \
  "${HOME}/.cache/pip" \
  "${HOME}/.cache/uv" \
  "${HOME}/.cache/ruff" \
  "${HOME}/.cache/mypy" \
  "${HOME}/.cache/pytest" \
  "${HOME}/.cache/coverage" \
  /commandhistory \
  /workspace/qdash/.venv \
  /workspace/qdash/ui/.next \
  /workspace/qdash/ui/node_modules
sudo chown -R "$(id -u):$(id -g)" \
  "${HOME}/.codex" \
  "${HOME}/.local" \
  "${HOME}/.cache" \
  /commandhistory \
  /workspace/qdash/.venv \
  /workspace/qdash/ui/.next \
  /workspace/qdash/ui/node_modules

# The Docker daemon resolves compose bind mounts on the host, so `docker compose`
# run from this container must see the checkout at its host path. Without the
# link, `./src` resolves to a /workspace/qdash/... path that does not exist on
# the host, and containers come up with empty bind mounts.
host_workspace="${QDASH_HOST_WORKSPACE:-}"
if [ -n "${host_workspace}" ] && [ "${host_workspace}" != "/workspace/qdash" ] \
  && [ ! -e "${host_workspace}" ]; then
  sudo mkdir -p "$(dirname "${host_workspace}")"
  sudo ln -s /workspace/qdash "${host_workspace}"
fi

touch ~/.bashrc ~/.zshrc

grep -q 'umask 022' ~/.bashrc || echo 'umask 022' >> ~/.bashrc
grep -q 'umask 022' ~/.zshrc || echo 'umask 022' >> ~/.zshrc

tmp_zshrc="$(mktemp)"
awk '
  BEGIN { skip = 0 }
  /^# >>> qdash managed zsh >>>$/ { skip = 1; next }
  /^# <<< qdash managed zsh <<<$/{ skip = 0; next }
  /^# qdash git branch prompt$/ { skip = 1; next }
  skip && /^PROMPT='\''%n@%m %1~\$\{vcs_info_msg_0_\} %# '\''$/ { skip = 0; next }
  !skip { print }
' ~/.zshrc > "${tmp_zshrc}"

cat <<'EOF' >> "${tmp_zshrc}"

# >>> qdash managed zsh >>>
if [ -f /workspace/qdash/.devcontainer/zshrc.qdash ]; then
  source /workspace/qdash/.devcontainer/zshrc.qdash
elif [ -f /opt/qdash-devcontainer/zshrc.qdash ]; then
  source /opt/qdash-devcontainer/zshrc.qdash
fi
# <<< qdash managed zsh <<<
EOF

mv "${tmp_zshrc}" ~/.zshrc
