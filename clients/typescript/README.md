# @oqtopus-team/qdash-client

Typed QDash API access for Node.js 20 or later.

```bash
npm install @oqtopus-team/qdash-client
```

```ts
import { QDashClient } from "@oqtopus-team/qdash-client";

const client = QDashClient.fromEnv();
const chip = await client.getDefaultChip();
console.log((await client.getChipMetrics(chip.chip_id)).qubit_metrics);
```

Set `QDASH_BASE_URL` (including `/api`), `QDASH_API_TOKEN`, and `QDASH_PROJECT_ID`.
Alternatively, `await QDashClient.fromProfile("local")` loads a shared Python/TypeScript profile.
See the [client reference](https://oqtopus-team.github.io/qdash/reference/clients/typescript)
for configuration, generated endpoints, and the calibration SDK.

## Development

Run from the repository root:

```bash
bun install --frozen-lockfile
task test-client-ts
task build-client-ts
```

After API changes, run `task generate`; never edit `src/generated/` manually.
Client, SDK, and pi packages share QDash's release version. See
[package releases](../../docs/developer-guide/agent/packages.md).
