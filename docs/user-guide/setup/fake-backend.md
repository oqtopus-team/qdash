# Fake Backend Setup

Use the Fake backend to evaluate QDash pages, workflows, persistence, and result handling without
connecting quantum hardware.

Complete [Prepare the Host](../setup.md#prepare-the-host), then create `.env` from the default
example:

```bash
cp .env.example .env
```

Keep these backend values:

```dotenv
ENV=dev-fake
DEFAULT_BACKEND=fake
```

The Fake backend exposes simulated calibration tasks. It does not read Qubex hardware
configuration or open a hardware session. Database records, task results, figures, and other
QDash state still persist in the paths configured in `.env`.

Set the administrator credentials and any shared deployment options in
[Configure Shared Deployment Settings](../setup.md#configure-shared-deployment-settings), then
[start QDash](../setup.md#start-qdash).
