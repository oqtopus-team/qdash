# AI Setup

AI chat and figure analysis need model endpoints in `.env`; QDash starts and runs calibrations
without them. Configure AI after [Setup](../setup.md) has a running deployment you can sign in to.

The AI runtime and its workspace start with the standard Compose stack. Internal authentication
is generated automatically; no AI service profile or UI enable flag is required.

## Connect Model Endpoints

Set the `OPENAI_COMPATIBLE_BASE_URL_CHAT` and `OPENAI_COMPATIBLE_API_KEY_CHAT` pair in `.env`
for chat, and the corresponding `EVALUATION` pair for figure analysis. Base URLs must include
`/v1`. Select models in `config/copilot/chat.yaml` and `config/copilot/evaluation.yaml`.

Copilot can propose supported write operations without an extra enable setting. The signed-in
user must approve each proposed write in the chat, and their project permissions still apply.
The retired `AGENT_RUNTIME_ENABLE_WRITE_TOOLS` variable has no effect and can be removed from
existing `.env` files.

[Apply the changes](#apply-ai-changes) after editing `.env`.

## Add a Classifier

A classifier model chooses how the chat lays out the values it found: a calibration summary, an
execution comparison, or a failure list. The chat also asks it when its next step depends on a
judgment between a few categories: what kind of request a message is, which kind of problem a
failure points to, which check to run next, or which other view suits the values. The chat's
steps then show **Classifying** and the category the classifier chose. No classifier endpoint
is preconfigured: you supply its URL and token. Until both are set, the chat composes its own
views and makes such judgments itself.

1. Set the endpoint's URL, up to the API version, and its token in `.env`:

   ```dotenv
   CLASSIFIER_BASE_URL=https://classifier.example/v1
   CLASSIFIER_API_KEY=<api-token>
   ```

2. [Apply the changes](#apply-ai-changes). The runtime log reports
   `present_results: classifier system-one-classifier/ZefanCai/Open-Jev-2B` and
   `classify: classifier system-one-classifier/ZefanCai/Open-Jev-2B`, or why they are not
   offered, such as an unset variable.

The model is declared in `config/copilot/classifier.yaml`. To turn the classifier off, leave the
variables unset or remove the model from that file.

How this works: [Copilot architecture](../../developer-guide/copilot/architecture.md#presentation-classifier).

## Authenticate AI Endpoints with Cloudflare Access

Use one Cloudflare Access service token for chat and figure analysis. Create the token and add it
to a **Service Auth** policy on each AI endpoint's Access application, following
[Cloudflare's service token instructions](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/).

Set the shared credentials in `.env`:

```dotenv
CF_ACCESS_CLIENT_ID=<service-token-client-id>
CF_ACCESS_CLIENT_SECRET=<service-token-client-secret>
```

Keep the existing `OPENAI_COMPATIBLE_BASE_URL_CHAT` and `OPENAI_COMPATIBLE_BASE_URL_EVALUATION`
settings pointed at the protected HTTPS URLs, including `/v1`. The shared token is sent to every
endpoint configured through `base_url: env:OPENAI_COMPATIBLE_BASE_URL_<SUFFIX>`, including custom
suffixes, and to a classifier configured through `base_url: env:CLASSIFIER_BASE_URL` or
`env:CLASSIFIER_BASE_URL_<SUFFIX>`.
Literal URLs and built-in providers do not receive it.

Keep each endpoint's API key if the model server requires it. If authentication is handled only
by Cloudflare Access, leave that API key empty. Both Access values must be set together; leave
both empty to keep using API-key-only authentication.

## Apply AI Changes

Recreate the runtime to load changed `.env` values:

```bash
docker compose up -d --build --force-recreate agent-runtime
```

The Pi runtime stores resumable conversation state in the `agent-runtime-state` volume, which
container recreation preserves. Use [AI Chat](../ai-chat.md) and
[AI Evaluations](../ai-evaluations.md) once the endpoints are configured.
