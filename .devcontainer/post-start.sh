#!/usr/bin/env bash
set -euo pipefail

sudo mkdir -p \
  "${HOME}/.codex" \
  "${HOME}/.local" \
  "${HOME}/.cache/pip" \
  "${HOME}/.cache/uv" \
  /commandhistory \
  /workspace/qdash/ui/node_modules
sudo chown -R "$(id -u):$(id -g)" \
  "${HOME}/.codex" \
  "${HOME}/.local" \
  "${HOME}/.cache" \
  /commandhistory \
  /workspace/qdash/ui/node_modules

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
