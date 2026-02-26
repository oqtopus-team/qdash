---
layout: doc
---

# Quick Start

## Install

```bash
git clone https://github.com/oqtopus-team/qdash.git
```

## Initial Setup

Create a directory for PostgreSQL.

```bash
mkdir postgres_data
```

Create the environment file from the example.

```bash
cp .env.example .env
cp -r config/qubex/qubex.example/* config/qubex/
```

## Start the Application

```bash
docker compose up -d
```

You can now access the application at <a href="http://localhost:5714/signup"> localhost:5714 </a>.

## Sign in

![login](/images/login.png)

Default admin password is written in the `.env` file under `ADMIN_PASSWORD` variable.
You can now access the application at <a href="http://localhost:5714/execution"> localhost:5714 </a>.

## Remote access (Cloudflare Tunnel)

You can share QDash securely without opening extra ports by using Cloudflare Tunnel.

1. Create a tunnel in the Cloudflare dashboard and copy the issued `TUNNEL_TOKEN`.
2. Add the token to your `.env` file (e.g. `TUNNEL_TOKEN=...`).
3. Start the tunnel with `docker compose --profile tunnel up -d tunnel`.
4. Confirm in the Cloudflare dashboard that the tunnel status is “Connected”.

Once connected, the hostname provided by Cloudflare (for example `https://your-tunnel.example.com`) will serve the same UI experience as `http://localhost:5714`, including charts and figures.
