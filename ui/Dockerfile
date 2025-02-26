FROM node:18-alpine

WORKDIR /app

COPY ./ui .

# Install dependencies with legacy peer deps to handle version conflicts
RUN npm install --legacy-peer-deps

ENV HOST 0.0.0.0
ENV PORT 5714
ENV NEXT_TELEMETRY_DISABLED 1

CMD ["npm", "run", "dev", "--", "-p", "5714"]
