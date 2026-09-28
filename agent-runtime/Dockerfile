FROM node:22-slim

WORKDIR /app

# Isolate pi's config/package directory from any global ~/.pi/agent.
ENV PI_CODING_AGENT_DIR=/app/.pi-agent
ENV AGENT_WORK_DIR=/app/workspace

COPY agent-runtime/package.json ./
RUN npm install

# Install the QDash extension into the agent dir at build time so startup needs
# no network access. The install step also creates the agent dir, into which the
# runtime generates models.json from chat.yaml at startup.
RUN npx --yes @earendil-works/pi-coding-agent install npm:@oqtopus-team/pi-qdash

COPY agent-runtime/src ./src
RUN mkdir -p $AGENT_WORK_DIR

CMD ["npx", "tsx", "src/server.ts"]
