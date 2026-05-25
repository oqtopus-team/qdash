---
layout: doc
---

# Quick Start

## Install

```bash
git clone https://github.com/oqtopus-team/qdash.git
cd qdash
```

## Initial Setup

Create the environment file from the example and install local dependencies.

```bash
cp .env.example .env
task dev-local-setup
```

The setup task installs Python and UI dependencies and creates the default Qubex config
directory. Edit `.env` if you need different ports, data directories, or admin credentials.

## Start the Application

For the full Docker Compose stack, run:

```bash
task deploy-local
```

For a lighter host-side development stack, run:

```bash
task dev-local
```

You can now access the application at <a href="http://localhost:5714/login"> localhost:5714 </a>.

## Sign in

![login](/images/login.png)

The default admin username and password are written in `.env` as `QDASH_ADMIN_USERNAME` and
`QDASH_ADMIN_PASSWORD`.
After signing in, the app redirects to the default authenticated page.

## Remote access (Cloudflare Tunnel)

You can share QDash securely without opening extra ports by using Cloudflare Tunnel.

1. Create a tunnel in the Cloudflare dashboard and copy the issued `TUNNEL_TOKEN`.
2. Add the token to your `.env` file (e.g. `TUNNEL_TOKEN=...`).
3. Start the tunnel with `task deploy`.
4. Confirm in the Cloudflare dashboard that the tunnel status is “Connected”.

Once connected, the hostname provided by Cloudflare (for example `https://your-tunnel.example.com`) will serve the same UI experience as `http://localhost:5714`, including charts and figures.
Configure the tunnel public hostname service URL to `http://reverse-proxy:80`. The Compose reverse
proxy serves the UI and `/api/*` from the main hostname; optional Prefect and Mongo Express
hostnames can point to the same service URL when remote operator access is needed.
`task deploy` validates the tunnel token and reverse-proxy hostname settings before starting the
stack; it does not rewrite `.env`.
