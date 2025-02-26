#!/bin/bash

env_content='ENV="oqtopus"
CLIENT_URL=http://ui:5714
SLACK_BOT_TOKEN=""
POSTGRES_DATA_PATH="./postgres_data"
MONGO_DATA_PATH="./mongo_data/data/db"
CALIB_DATA_PATH="./calib_data"
PREFECT_HOST="172.22.0.5"
POSTGRES_HOST="172.22.0.4"
QDASH_SERVER_HOST="localhost"
MONGO_HOST="172.22.0.2"
QPU_DATA_PATH="./qpu_data"'

echo "$env_content" > .env

echo "Created .env file"

echo "" > .slack.env
