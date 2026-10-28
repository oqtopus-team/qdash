#!/bin/sh
set -eu

invalid_origin() {
  echo "HTTPS mode requires CLIENT_URL=https://<host>[:443][/]. Paths, credentials, queries, fragments, and other ports are unsupported." >&2
  exit 1
}

case "${CLIENT_URL:-}" in
  https://*) ;;
  *) invalid_origin ;;
esac

site_address="${CLIENT_URL%/}"
authority="${site_address#https://}"
case "$authority" in
  */* | *\?* | *\#* | *@* | *[[:space:]]* | *\\*) invalid_origin ;;
esac

case "$authority" in
  \[*\]) host="$authority" ;;
  \[*\]:443) host="${authority%:443}" ;;
  \[*) invalid_origin ;;
  *:443) host="${authority%:443}" ;;
  *:*) invalid_origin ;;
  *) host="$authority" ;;
esac

case "$host" in
  "" | "[]" | [!\[]*:*) invalid_origin ;;
esac

export CADDY_SITE_ADDRESS="$site_address"
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
