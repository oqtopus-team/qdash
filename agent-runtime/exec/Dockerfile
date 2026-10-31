# The Copilot workspace: the container behind the chat's bash/read/write/edit
# tools. It holds no QDash credentials and joins no QDash network; the Agent
# Runtime reaches it only through exec/server.ts, which starts one pi-env
# daemon per conversation as that user's own uid.
#
# Build context: repository root (see compose.yaml).

# The pi-env daemon ships inside the npm package the runtime depends on.
FROM oven/bun:1.4.0 AS daemon
WORKDIR /app
COPY package.json bun.lock ./
COPY agent-runtime/package.json ./agent-runtime/package.json
COPY packages/pi-qdash/package.json ./packages/pi-qdash/package.json
COPY packages/pi-qcaleval/package.json ./packages/pi-qcaleval/package.json
COPY clients/typescript/package.json ./clients/typescript/package.json
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile
RUN set -eu; arch="$(uname -m)"; \
    case "$arch" in x86_64) arch=x64 ;; aarch64) arch=arm64 ;; esac; \
    cp "agent-runtime/node_modules/@earendil-works/pi-env/bin/pi-env-linux-$arch/pi-env" /pi-env

FROM python:3.11-slim-bookworm
COPY agent-runtime/exec/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
# bun runs the server; the daemon binary needs nothing else.
COPY --from=oven/bun:1.4.0 /usr/local/bin/bun /usr/local/bin/bun
COPY --from=daemon /pi-env /usr/local/bin/pi-env
COPY agent-runtime/exec /app/exec
ENV PYTHONDONTWRITEBYTECODE=1 \
    BUN_RUNTIME_TRANSPILER_CACHE_PATH=/tmp/bun-cache \
    AGENT_EXEC_WORKSPACE_ROOT=/workspace \
    AGENT_EXEC_DAEMON=/usr/local/bin/pi-env
RUN mkdir -p /workspace
VOLUME /workspace
# Root, so each owner's daemon can be started as its own uid (setpriv).
CMD ["bun", "/app/exec/server.ts"]
