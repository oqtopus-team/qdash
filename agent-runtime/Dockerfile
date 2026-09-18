FROM node:22-slim

WORKDIR /app

# Isolate pi's config/package directory from any global ~/.pi/agent.
ENV PI_CODING_AGENT_DIR=/app/.pi-agent
ENV AGENT_WORK_DIR=/app/workspace

COPY agent-runtime/package.json ./
RUN npm install

# Install the QDash extension into the agent dir at build time so startup needs
# no network access. This must run before models.json is copied, because the
# install step creates the agent dir.
RUN npx --yes @earendil-works/pi-coding-agent install npm:@oqtopus-team/pi-qdash

COPY agent-runtime/models.json $PI_CODING_AGENT_DIR/models.json
COPY agent-runtime/src ./src
RUN mkdir -p $AGENT_WORK_DIR

CMD ["npx", "tsx", "src/server.ts"]
