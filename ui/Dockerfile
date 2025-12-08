ARG NEXT_PUBLIC_API_URL=/api
ARG NEXT_PUBLIC_PREFECT_URL
ARG INTERNAL_API_URL

FROM oven/bun:1 AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

FROM base AS deps
COPY ./ui/package.json ./package.json
COPY ./ui/bun.lock ./bun.lock
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

FROM deps AS builder
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_PREFECT_URL
ARG INTERNAL_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_PREFECT_URL=$NEXT_PUBLIC_PREFECT_URL
ENV INTERNAL_API_URL=$INTERNAL_API_URL
COPY ./ui .
RUN bun run build

FROM oven/bun:1 AS runner
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_PREFECT_URL
ARG INTERNAL_API_URL
WORKDIR /app
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_PREFECT_URL=$NEXT_PUBLIC_PREFECT_URL
ENV INTERNAL_API_URL=$INTERNAL_API_URL

COPY ./ui/package.json ./package.json
COPY ./ui/bun.lock ./bun.lock
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile --production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY ./ui/next.config.js ./next.config.js

CMD ["sh", "-c", "bun run start --hostname 0.0.0.0 --port ${UI_PORT:-${PORT:-5714}}"]
