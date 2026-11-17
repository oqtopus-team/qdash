# AI Setup

After [Setup](../setup.md), configure model endpoints in `.env` to enable AI chat and evaluations.
QDash runs calibrations without AI endpoints.

| Setting | Needed for | Required |
| --- | --- | --- |
| [Chat endpoint](#connect-model-endpoints) | **AI Chat**, the **Ask AI** sidebar, and forum AI replies | For chat |
| [Evaluation endpoint](#connect-model-endpoints) | **AI Evaluations** and **Evaluate** on **Chip** | For evaluations |
| [Deployment profile](#select-a-deployment-profile) | Chat and evaluation models specific to this deployment | No |
| [Classifier endpoint](#add-a-classifier) | Fixed result layouts and category judgments in chat | No |
| [Cloudflare Access service token](#authenticate-ai-endpoints-with-cloudflare-access) | Endpoints behind Cloudflare Access | Only for such endpoints |
| [ChatGPT plan connections](#let-users-connect-their-chatgpt-plan) | Users answering their own chats with their ChatGPT plan | No |

The AI runtime and its workspace start with the standard Compose stack. QDash generates their
internal authentication; no AI Compose profile or UI enable flag is needed.

## Connect Model Endpoints

1. Set the endpoint URL and API key for each AI feature you use in `.env`. Each base URL must end
   with `/v1`:

   | Variables | Feature |
   | --- | --- |
   | `OPENAI_COMPATIBLE_BASE_URL_CHAT` / `OPENAI_COMPATIBLE_API_KEY_CHAT` | Chat |
   | `OPENAI_COMPATIBLE_BASE_URL_EVALUATION` / `OPENAI_COMPATIBLE_API_KEY_EVALUATION` | Figure evaluation |

2. Select the models in `config/copilot/chat.yaml` and `config/copilot/evaluation.yaml`, or
   [select a deployment profile](#select-a-deployment-profile). The supplied files reference the
   variables above. Further endpoints, provider names, and
   gateway compatibility keys are described in
   [Copilot Model Configuration](../../developer-guide/copilot/model-configuration.md).
3. [Apply the changes](#apply-ai-changes).

Copilot write operations require your approval and project permissions. No extra enable setting
is needed; the retired `AGENT_RUNTIME_ENABLE_WRITE_TOOLS` variable has no effect and can be removed.

## Select a Deployment Profile

A deployment profile gives one deployment its own chat and evaluation models while the default
files stay unchanged for other deployments. Each profile is a directory under
`config/copilot/profiles/`. The supplied `oqtopus` profile is a sample that names
`Qwen/Qwen3.8-27B` for chat and evaluation; it has not been tested against any serving API.

1. Confirm that the deployment serving the profile's models meets what the profile assumes, and
   edit the profile where it does not. For `oqtopus`, the serving API must offer OpenAI-compatible
   Chat Completions for `Qwen/Qwen3.8-27B` and accept image input for evaluation, and its
   maximum context length and output limit must cover the profile's `num_ctx` and
   `max_output_tokens`. QDash checks the profile's settings, not the endpoint.
2. Set the profile name in `.env`:

   ```dotenv
   QDASH_COPILOT_PROFILE=oqtopus
   ```

   Leave the value unset or empty to use `config/copilot/chat.yaml` and
   `config/copilot/evaluation.yaml`.
3. Set the endpoint variables of [Connect Model Endpoints](#connect-model-endpoints) for the
   endpoints the profile serves. The `oqtopus` profile uses the `CHAT` and `EVALUATION` pairs.
4. Recreate the API and the AI runtime. A restart keeps the environment a container was created
   with, so it does not apply a changed `.env` value:

   ```bash
   docker compose up -d --no-deps --force-recreate api agent-runtime
   ```

   With the host-side development stack, stop and rerun `task dev-api-local`, then recreate the
   runtime with
   `docker compose -f compose.yaml -f compose.dev-local.yaml up -d --no-deps --force-recreate agent-runtime`.
5. Check the runtime log with `docker compose logs agent-runtime`. It reports
   `copilot models: profile oqtopus` and the two files it read.

QDash does not fall back to the default models when a profile is misconfigured. If the name is
invalid, the profile directory or one of its files is missing, or a model setting is missing,
unknown, or has a value of the wrong type or range, the AI runtime stops at startup, Copilot
requests fail, and the logs of both services name the file, the model entry, and the setting.
Fix the profile or the variable and recreate both services again. To add a profile for another
deployment, see
[Deployment Profiles](../../developer-guide/copilot/model-configuration.md#deployment-profiles).

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

## Let Users Connect Their ChatGPT Plan

Each QDash user can connect their own ChatGPT account in **Settings → Copilot** and send their
chats to ChatGPT models on their own ChatGPT plan; see
[Use Your ChatGPT Plan](../ai-chat.md#use-your-chatgpt-plan). The deployment's chat and evaluation
models keep working as before, and nothing else runs on a user's plan. No operator API key is
involved, and no user's chat ever falls back to the deployment's OpenAI key or another user's
connection.

The Compose stack enables connections without configuration: it generates the key that encrypts
users' ChatGPT sign-ins into the `credential-key` volume, which only the API mounts. Back up that
volume with MongoDB; without it, stored connections cannot be read and every user connects again.
The API must reach `auth.openai.com` and `api.openai.com`; an HTTPS proxy in its environment is
used.

| Variable | Meaning | Default |
| --- | --- | --- |
| `QDASH_CREDENTIAL_KEY` | Fernet keys, comma-separated, newest first; set only for an API started on the host, never in a `.env` that the runtime also reads | Compose: the generated key file |
| `QDASH_CREDENTIAL_KEY_FILE` | File holding the keys instead | Compose: `/run/qdash-credential-key/key` |
| `QDASH_CHATGPT_CALLBACK_PORT` | Port of the `http://127.0.0.1:<port>/auth/callback` address users copy back after signing in | `1455` |

To rotate the key, put a new key in front of the old one, recreate `api`, and drop the old key
once users have signed in again or refreshed. Without any key, **Settings → Copilot** tells users
that connections are not set up. OpenAI documents ChatGPT plan usage for open-source and locally
hosted apps; see [ChatGPT plan usage](https://developers.openai.com/siwc/token-sharing-open-source)
for the conditions that apply to other deployments.

## Apply AI Changes

Recreate the runtime to load changed `.env` values:

```bash
docker compose up -d --build --force-recreate agent-runtime
```

Recreating the runtime keeps saved conversations: they are stored in the `agent-runtime-state`
volume. Continue with [AI Chat](../ai-chat.md) and [AI Evaluations](../ai-evaluations.md).
