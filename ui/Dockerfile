FROM node:18-alpine

WORKDIR /app

COPY ./ui/package*.json  ./
RUN npm install

ENV HOST 0.0.0.0
ENV PORT 5714
ENV NEXT_TELEMETRY_DISABLED 1

CMD ["npm", "run", "dev", "--", "-p", "5714"]
