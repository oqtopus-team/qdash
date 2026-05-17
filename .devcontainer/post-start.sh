#!/usr/bin/env bash
set -euo pipefail

mkdir -p /root/.codex /root/.local
mkdir -p /root/.cache/pip /root/.cache/uv /workspace/qdash/ui/node_modules
chmod -R u+rwX \
  /root/.codex \
  /root/.local \
  /root/.cache/pip \
  /root/.cache/uv \
  /workspace/qdash/ui/node_modules

git config --global --get-all safe.directory | grep -Fxq /workspace/qdash \
  || git config --global --add safe.directory /workspace/qdash

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
[ -f /workspace/qdash/.devcontainer/zshrc.qdash ] && source /workspace/qdash/.devcontainer/zshrc.qdash
# <<< qdash managed zsh <<<
EOF

mv "${tmp_zshrc}" ~/.zshrc
