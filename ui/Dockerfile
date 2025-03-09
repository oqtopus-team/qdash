FROM oven/bun:1

WORKDIR /app

# First copy package files
COPY ./ui/package.json ./
COPY ./ui/bun.lock ./

# Install dependencies
RUN bun install

# Then copy the rest of the files
COPY ./ui .

ENV HOST 0.0.0.0
ENV PORT 5714
ENV NEXT_TELEMETRY_DISABLED 1

# Start the development server
CMD ["bun", "run", "dev"]
