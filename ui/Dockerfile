FROM node:18-alpine

WORKDIR /app

# First copy package files
COPY ./ui/package*.json ./

# Install dependencies with legacy peer deps to handle version conflicts
RUN npm install --legacy-peer-deps

# Then copy the rest of the files
COPY ./ui .

ENV HOST 0.0.0.0
ENV PORT 5714
ENV NEXT_TELEMETRY_DISABLED 1

# Start the development server
CMD ["npm", "run", "dev"]
