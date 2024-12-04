FROM node:18-alpine

WORKDIR /app

COPY ./client/package*.json  ./
# pnpm をインストール
#RUN npm install -g pnpm
# RUN pnpm install
RUN npm install
ENV HOST 0.0.0.0
CMD ["npm", "run", "dev"]
