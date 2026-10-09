FROM oven/bun:1.4.0

WORKDIR /app

# Isolate pi's config/package directory from any global ~/.pi/agent.
ENV PI_CODING_AGENT_DIR=/app/.pi-agent
ENV AGENT_WORK_DIR=/app/workspace

COPY agent-runtime/package.json agent-runtime/bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

# Pi shells out to its configured package manager when installing extensions and
# defaults to npm, which this image does not have. Must be written before the
# install step below.
RUN mkdir -p $PI_CODING_AGENT_DIR \
    && echo '{"npmCommand": ["bun"]}' > $PI_CODING_AGENT_DIR/settings.json

# Install the QDash extension into the agent dir at build time so startup needs
# no network access. The agent dir is also where the runtime generates
# models.json from chat.yaml at startup.
RUN bunx @earendil-works/pi-coding-agent install npm:@oqtopus-team/pi-qdash@0.1.10-beta.15
# pi-qcaleval is trusted as a whole (TRUSTED_EXTENSION_PACKAGES in
# src/allowed-tools.ts), so this pin is its release gate.
RUN bunx @earendil-works/pi-coding-agent install npm:@orangekame3/pi-qcaleval@0.0.1

COPY agent-runtime/src ./src
# The agent dir and workspace are written at runtime (models.json, agent files),
# so hand /app to the unprivileged user the base image ships before dropping root.
RUN mkdir -p $AGENT_WORK_DIR /app/state && chown -R bun:bun /app
USER bun

CMD ["bun", "src/server.ts"]
