# AI Setup

Configure model endpoints after [Setup](../setup.md) to enable chat and evaluations. Calibration
runs do not require AI.

## Connect Model Endpoints

Set the credentials needed by your models in `.env`. Endpoint base URLs end with `/v1`.

| Variables | Default use |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI chat |
| `ANTHROPIC_API_KEY` | Anthropic chat |
| `OPENAI_COMPATIBLE_BASE_URL_DEEPSEEK`, `OPENAI_COMPATIBLE_API_KEY_DEEPSEEK` | DeepSeek chat |
| `OPENAI_COMPATIBLE_BASE_URL_CHAT`, `OPENAI_COMPATIBLE_API_KEY_CHAT` | OpenAI-compatible chat |
| `OPENAI_COMPATIBLE_BASE_URL_EVALUATION`, `OPENAI_COMPATIBLE_API_KEY_EVALUATION` | Figure evaluation |

Models are configured in `config/agent/chat.yaml` and `config/agent/evaluation.yaml`.
Chat menus hide models whose credentials are missing. The first available model in configuration
order is the default. If none are available, configure a key before sending a message. An explicitly
selected model that fails does not switch providers. Apply changes as below. Writes still need
user approval and project permission.

For the supplied DeepSeek preview model, set `OPENAI_COMPATIBLE_BASE_URL_DEEPSEEK` to your
provider's base URL ending with `/v1` and `OPENAI_COMPATIBLE_API_KEY_DEEPSEEK` to your API token.
The endpoint is empty in the environment templates; choose a provider that serves the configured model.
After applying changes, select **preview/DeepSeek-V4.1-Flash-1017** in the chat model menu.
Preview model availability can change; check the provider's model list if requests fail.

## Select a Deployment Profile

Set `QDASH_AGENT_PROFILE` to a directory under `config/agent/profiles/`, or leave it empty for
the default files. Review model names, image support, context size, and output limits against
the serving API; the supplied `oqtopus` profile is an untested sample.

Recreate both services after changing the profile:

```bash
docker compose up -d --no-deps --force-recreate api agent-runtime
```

Check `docker compose logs agent-runtime` for the selected profile. Invalid profiles stop AI
startup rather than falling back. For host-side development, restart `task dev-api-local` and
recreate the runtime with the development Compose files. See
[model configuration](../../developer-guide/agent/model-configuration.md).

## Add a Classifier

An optional classifier helps choose result layouts and categories:

```dotenv
CLASSIFIER_BASE_URL=https://classifier.example/v1
CLASSIFIER_API_KEY=<api-token>
```

Its model lives in `config/agent/classifier.yaml`. Without it, chat makes these choices itself.
Apply changes and check the runtime log for classifier availability.

## Authenticate AI Endpoints with Cloudflare Access

Create a service token and add it to each endpoint's **Service Auth** policy, then set:

```dotenv
CF_ACCESS_CLIENT_ID=<service-token-client-id>
CF_ACCESS_CLIENT_SECRET=<service-token-client-secret>
```

Set both values or neither. They apply to endpoints configured through
`env:OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>` and `env:CLASSIFIER_BASE_URL` (including suffixes),
not literal URLs or built-in providers. Keep protected HTTPS URLs ending in `/v1`.
Keep API keys when the server requires them; classifiers always need a nonempty API key.

## Apply AI Changes

Recreate the runtime to load changed environment values:

```bash
docker compose up -d --build --force-recreate agent-runtime
```

Conversations remain in the `agent-runtime-state` volume. Open **Agent**, select a configured
model, and send a short message to verify chat. For figure evaluation, open a completed task result and follow [AI Evaluations](../ai-evaluations.md);
a successful chat does not verify the separate evaluation endpoint.

To supply shared task knowledge, set `KNOWLEDGE_REPO_URL` in `.env` and run
`task knowledge-pull` (requires Go Task and read access to that repository). Confirm the tasks
appear on **Knowledge** before relying on their guidance.
