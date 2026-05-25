#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=".env"

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
      print line
      exit
    }
  ' "$ENV_FILE"
}

missing=0
for key in TUNNEL_TOKEN QDASH_HOST CLIENT_URL NEXT_PUBLIC_API_URL QDASH_UI_UPSTREAM QDASH_API_UPSTREAM; do
  if [ -z "$(env_value "$key")" ]; then
    echo "Missing required deploy setting: $key" >&2
    missing=1
  fi
done

for key in QDASH_UI_UPSTREAM QDASH_API_UPSTREAM; do
  value="$(env_value "$key")"
  case "$value" in
    *'$'*|*:)
      echo "Invalid deploy setting: $key=$value" >&2
      echo "Use an explicit Docker service upstream, for example ui:5714 or api:5715." >&2
      missing=1
      ;;
  esac
done

if [ "$missing" -ne 0 ]; then
  echo "Set Cloudflare deploy settings in .env before running task deploy." >&2
  echo "Cloudflare public hostname service URL should be: http://reverse-proxy:80" >&2
  exit 1
fi

case "$(env_value CLIENT_URL)" in
  http://*.localhost:*|https://*.localhost:*)
    echo "WARNING: CLIENT_URL points to .localhost; this is usually not intended for Cloudflare deploy." >&2
    ;;
esac

echo "Deploy env looks ready for $(env_value QDASH_HOST)."
