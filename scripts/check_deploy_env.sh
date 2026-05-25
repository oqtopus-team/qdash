#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing .env. Create it with: cp .env.example .env" >&2
  exit 1
fi

env_value() {
  local key="$1"
  awk -v key="$key" '
    $0 ~ "^[[:space:]]*(export[[:space:]]+)?" key "[[:space:]]*=" {
      line = $0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      sub("^[[:space:]]*" key "[[:space:]]*=", "", line)
      sub(/[[:space:]]+#.*/, "", line)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
      gsub(/^"|"$/, "", line)
      gsub(/^'\''|'\''$/, "", line)
      value = line
    }
    END { print value }
  ' "$ENV_FILE"
}

missing=0
for key in TUNNEL_TOKEN QDASH_HOST; do
  if [ -z "$(env_value "$key")" ]; then
    echo "Missing required deploy setting: $key" >&2
    missing=1
  fi
done

for key in ENV COMPOSE_PROJECT_NAME QDASH_HOST QDASH_LOCAL_HOST CLIENT_URL NEXT_PUBLIC_PREFECT_URL PROXY_PORT PREFECT_FORWARD_PORT; do
  count="$(
    awk -v key="$key" '
      $0 ~ "^[[:space:]]*(export[[:space:]]+)?" key "[[:space:]]*=" { count++ }
      END { print count + 0 }
    ' "$ENV_FILE"
  )"
  if [ "$count" -gt 1 ]; then
    echo "WARNING: $key is defined $count times in .env; the last value wins." >&2
  fi
done

for key in QDASH_UI_UPSTREAM QDASH_API_UPSTREAM; do
  value="$(env_value "$key")"
  case "$value" in
    *'$'*|*:)
      echo "WARNING: $key=$value will be overridden by task deploy." >&2
      ;;
  esac
done

for key in MONGO_PORT MONGO_EXPRESS_PORT POSTGRES_PORT PREFECT_PORT PREFECT_FORWARD_PORT API_PORT UI_PORT; do
  value="$(env_value "$key")"
  if [ -n "$value" ]; then
    case "$value" in
      *[!0-9]*)
        echo "Invalid deploy setting: $key=$value" >&2
        echo "$key must be an integer or removed from .env so the application default is used." >&2
        missing=1
        ;;
    esac
  elif grep -Eq "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$ENV_FILE"; then
    echo "Invalid deploy setting: $key is empty" >&2
    echo "$key must be an integer or removed from .env so the application default is used." >&2
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "Set Cloudflare deploy settings in .env before running task deploy." >&2
  echo "Cloudflare public hostname service URL should be: http://reverse-proxy:80" >&2
  exit 1
fi

client_url="$(env_value CLIENT_URL)"
case "$client_url" in
  ""|*'$'*)
    client_url="https://$(env_value QDASH_HOST)"
    ;;
esac

case "$client_url" in
  http://*.localhost:*|https://*.localhost:*)
    echo "WARNING: CLIENT_URL points to .localhost; this is usually not intended for Cloudflare deploy." >&2
    ;;
esac

echo "Deploy env looks ready for $(env_value QDASH_HOST)."
