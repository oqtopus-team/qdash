# AI Setup

After [Setup](../setup.md), configure model endpoints in `.env` to enable AI chat and evaluations.
QDash runs calibrations without AI endpoints.

| Setting | Needed for | Required |
| --- | --- | --- |
| [Chat endpoint](#connect-model-endpoints) | **AI Chat**, the **Ask AI** sidebar, and forum AI replies | For chat |
| [Evaluation endpoint](#connect-model-endpoints) | **AI Evaluations** and **Evaluate** on **Chip** | For evaluations |
| [Classifier endpoint](#add-a-classifier) | Fixed result layouts and category judgments in chat | No |
| [Cloudflare Access service token](#authenticate-ai-endpoints-with-cloudflare-access) | Endpoints behind Cloudflare Access | Only for such endpoints |

The AI runtime and its workspace start with the standard Compose stack. QDash generates their
internal authentication; no AI Compose profile or UI enable flag is needed.

## Connect Model Endpoints

1. Set the endpoint URL and API key for each AI feature you use in `.env`. Each base URL must end
   with `/v1`:

   | Variables | Feature |
   | --- | --- |
   | `OPENAI_COMPATIBLE_BASE_URL_CHAT` / `OPENAI_COMPATIBLE_API_KEY_CHAT` | Chat |
   | `OPENAI_COMPATIBLE_BASE_URL_EVALUATION` / `OPENAI_COMPATIBLE_API_KEY_EVALUATION` | Figure evaluation |

2. Select the models in `config/copilot/chat.yaml` and `config/copilot/evaluation.yaml`. The
   supplied files reference the variables above. Further endpoints, provider names, and
   gateway compatibility keys are described in
   [Copilot Model Configuration](../../developer-guide/copilot/model-configuration.md).
3. [Apply the changes](#apply-ai-changes).

Copilot write operations require your approval and project permissions. No extra enable setting
is needed; the retired `AGENT_RUNTIME_ENABLE_WRITE_TOOLS` variable has no effect and can be removed.

## Add a Classifier

A classifier optionally helps the chat:

- choose a fixed layout for values it found: a calibration summary, an execution comparison, or a
  failure list;
- classify requests and failures, or choose the next check.

The chat shows **Classifying** and the selected category. Without a classifier endpoint, the chat
chooses layouts and makes these judgments itself.

1. Set the endpoint's URL, up to the API version, and its token in `.env`:

   ```dotenv
   CLASSIFIER_BASE_URL=https://classifier.example/v1
   CLASSIFIER_API_KEY=<api-token>
   ```

2. [Apply the changes](#apply-ai-changes).
3. Check the runtime log with `docker compose logs agent-runtime`. It reports
   `present_results: classifier system-one-classifier/ZefanCai/Open-Jev-2B` and
   `classify: classifier system-one-classifier/ZefanCai/Open-Jev-2B`, or why they are not
   offered, such as an unset variable.

The model is declared in `config/copilot/classifier.yaml`. To turn the classifier off, leave the
variables unset or remove the model from that file. How this works:
[Presentation Classifier](../../developer-guide/copilot/model-configuration.md#presentation-classifier).

## Authenticate AI Endpoints with Cloudflare Access

Use one Cloudflare Access service token for the chat, evaluation, and classifier endpoints.

1. Create the token and add it to a **Service Auth** policy on each AI endpoint's Access
   application, following
   [Cloudflare's service token instructions](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/).
2. Set both credentials in `.env`:

   ```dotenv
   CF_ACCESS_CLIENT_ID=<service-token-client-id>
   CF_ACCESS_CLIENT_SECRET=<service-token-client-secret>
   ```

3. Keep `OPENAI_COMPATIBLE_BASE_URL_CHAT` and `OPENAI_COMPATIBLE_BASE_URL_EVALUATION` pointed at
   the protected HTTPS URLs, including `/v1`.
4. [Apply the changes](#apply-ai-changes).

The token is sent to every endpoint configured through
`base_url: env:OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>`, including custom suffixes, and to a
classifier configured through `base_url: env:CLASSIFIER_BASE_URL` or
`env:CLASSIFIER_BASE_URL_<SUFFIX>`. Literal URLs and built-in providers do not receive it.

Keep an endpoint's API key if its model server requires one. Chat and evaluation endpoints can
leave the key empty when Cloudflare Access alone authenticates them. The classifier still requires
a nonempty `CLASSIFIER_API_KEY` (or its configured suffixed variable), even with Access credentials.
Both Access values must be set together. Leave both empty to use API keys only.

## Apply AI Changes

Recreate the runtime to load changed `.env` values:

```bash
docker compose up -d --build --force-recreate agent-runtime
```

Recreating the runtime keeps saved conversations: they are stored in the `agent-runtime-state`
volume. Continue with [AI Chat](../ai-chat.md) and [AI Evaluations](../ai-evaluations.md).
