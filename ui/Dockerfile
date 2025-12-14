ARG NEXT_PUBLIC_API_URL=/api
ARG NEXT_PUBLIC_ENV
ARG NEXT_PUBLIC_PREFECT_URL
ARG INTERNAL_API_URL
ARG NEXT_PUBLIC_COPILOT_ENABLED

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
ARG NEXT_PUBLIC_ENV
ARG NEXT_PUBLIC_PREFECT_URL
ARG INTERNAL_API_URL
ARG NEXT_PUBLIC_COPILOT_ENABLED
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_ENV=$NEXT_PUBLIC_ENV
ENV NEXT_PUBLIC_PREFECT_URL=$NEXT_PUBLIC_PREFECT_URL
ENV INTERNAL_API_URL=$INTERNAL_API_URL
ENV NEXT_PUBLIC_COPILOT_ENABLED=$NEXT_PUBLIC_COPILOT_ENABLED
COPY ./ui .
# Use Turbopack for faster builds with build cache
RUN --mount=type=cache,target=/app/.next/cache \
    bun run next build --turbo

# Standalone output - no need for bun install in runner
FROM node:20-alpine AS runner
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_ENV
ARG NEXT_PUBLIC_PREFECT_URL
ARG INTERNAL_API_URL
ARG NEXT_PUBLIC_COPILOT_ENABLED
WORKDIR /app
ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_ENV=$NEXT_PUBLIC_ENV
ENV NEXT_PUBLIC_PREFECT_URL=$NEXT_PUBLIC_PREFECT_URL
ENV INTERNAL_API_URL=$INTERNAL_API_URL
ENV NEXT_PUBLIC_COPILOT_ENABLED=$NEXT_PUBLIC_COPILOT_ENABLED
# OPENAI_API_KEY is passed at runtime via environment variable

# Copy standalone output (includes minimal node_modules)
COPY --from=builder /app/.next/standalone ./
# Copy static files
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# Next.js standalone uses PORT and HOSTNAME env vars
ENV PORT=5714
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
