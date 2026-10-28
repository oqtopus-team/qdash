FROM oven/bun:1.4.0

WORKDIR /app

# Isolate pi's config/package directory from any global ~/.pi/agent.
ENV PI_CODING_AGENT_DIR=/app/.pi-agent
ENV AGENT_WORK_DIR=/app/workspace

# The runtime and its pi packages share the repository lockfile. UI and client
# workspaces retain their independent dependency installs.
COPY package.json bun.lock ./
COPY agent-runtime/package.json ./agent-runtime/package.json
COPY packages/pi-qdash ./packages/pi-qdash
COPY packages/pi-qcaleval ./packages/pi-qcaleval
RUN bun install --frozen-lockfile

WORKDIR /app/agent-runtime
COPY agent-runtime/src ./src
# exec/protocol.ts is shared with the Copilot workspace's server (exec/Dockerfile).
COPY agent-runtime/exec ./exec
# The agent dir and workspace are written at runtime (models.json, agent files),
# so hand /app to the unprivileged user the base image ships before dropping root.
RUN mkdir -p $PI_CODING_AGENT_DIR $AGENT_WORK_DIR /app/state && chown -R bun:bun /app
USER bun

CMD ["bun", "src/server.ts"]
