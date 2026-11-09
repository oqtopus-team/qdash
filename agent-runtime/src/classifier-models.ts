import { existsSync, readFileSync } from "node:fs";

import { createProvider, type ClassifierModel, type Provider } from "@earendil-works/pi-ai";
import { typesafeSystemOneApi } from "@earendil-works/pi-ai/api/typesafe-system-one.lazy";
import { parse } from "yaml";

import { CF_ACCESS_ENV, PROVIDER_ALIASES, resolveBaseUrl, usesCloudflareAccess } from "./models-config.ts";

/**
 * The classifier models of config/copilot/classifier.yaml, set up on pi's
 * model runtime.
 *
 * `classifier_models` lists the models a QDash feature may ask to classify,
 * as `chat_models` and `evaluation_models` list chat and evaluation models.
 * The first entry is the default. Declaring a model only makes it available:
 * each feature that classifies has its own switch (for `present_results`, the
 * `presentation` section of chat.yaml) and names, or defaults to, one of these.
 *
 * An entry is either a pi catalog classifier (provider and name only; its
 * credentials come from that provider's own variable) or a self-hosted System
 * One (TypeSafe Jev) endpoint QDash registers as its own `system-one-*`
 * provider. An entry whose model, endpoint or credentials are missing is
 * reported and left unavailable; nothing falls back to another provider.
 */

/**
 * A self-hosted System One endpoint, set like an OpenAI-compatible model
 * entry: settings name environment variables, never values, and those are
 * read when a request is made.
 */
export interface ClassifierEndpoint {
  /** `env:CLASSIFIER_BASE_URL[_<SUFFIX>]` or a URL up to the API version: requests go to `<base_url>/systemone`. */
  baseUrl: string;
  /** Variable holding the bearer token sent as `Authorization`. */
  apiKeyEnv: string;
}

export interface ClassifierModelConfig {
  /** pi provider id: a catalog provider (aliases resolved), or the endpoint's own `system-one-*` id. */
  provider: string;
  /** Model id: a catalog classifier, or what the endpoint receives as `model`. */
  name: string;
  /** A System One endpoint QDash registers as `provider`; absent for a pi catalog classifier. */
  endpoint?: ClassifierEndpoint;
}

/** Provider ids of System One endpoints, as `openai-compatible-*` is for chat. */
export const SYSTEM_ONE_PROVIDER_PREFIX = "system-one";
/**
 * Base URL variables that get the shared Cloudflare Access token:
 * CLASSIFIER_BASE_URL and CLASSIFIER_BASE_URL_<SUFFIX>, as
 * OPENAI_COMPATIBLE_BASE_URL_<SUFFIX> are for chat.
 */
export const CLASSIFIER_BASE_URL_ENV = "CLASSIFIER_BASE_URL";
const CLASSIFIER_ACCESS_VARIABLES = [CLASSIFIER_BASE_URL_ENV, `${CLASSIFIER_BASE_URL_ENV}_`] as const;
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;
const ENTRY_KEYS = new Set(["provider", "name", "base_url", "api_key_env"]);

export const classifierLabel = (model: Pick<ClassifierModelConfig, "provider" | "name">) =>
  `${model.provider}/${model.name}`;

/**
 * classifier.yaml's `classifier_models`, in order; empty when the file or the
 * list is absent. Throws on an invalid entry, so a typo is reported instead of
 * silently changing which model is used.
 */
export function classifierModelsFrom(classifierYaml: string | undefined): ClassifierModelConfig[] {
  if (classifierYaml === undefined) return [];
  const raw = (parse(classifierYaml) as Record<string, unknown> | null)?.classifier_models;
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) throw new Error("classifier_models must be a list");
  const models = raw.map((entry, index) => classifierEntry(entry, `classifier_models[${index}]`));
  const seen = new Set<string>();
  const endpointProviders = new Set<string>();
  for (const model of models) {
    const label = classifierLabel(model);
    if (seen.has(label)) throw new Error(`classifier_models lists ${label} twice`);
    seen.add(label);
    if (model.endpoint) {
      // One endpoint per provider id, so each keeps its own URL and token.
      if (endpointProviders.has(model.provider)) {
        throw new Error(`classifier_models: provider ${model.provider} names more than one endpoint`);
      }
      endpointProviders.add(model.provider);
    }
  }
  return models;
}

function classifierEntry(raw: unknown, where: string): ClassifierModelConfig {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) throw new Error(`${where} must be a mapping`);
  const entry = raw as Record<string, unknown>;
  const unknown = Object.keys(entry).filter((key) => !ENTRY_KEYS.has(key));
  if (unknown.length > 0) {
    throw new Error(
      `${where} has unknown keys ${unknown.join(", ")}; a feature's own settings belong in that feature's section`,
    );
  }
  const { provider, name } = entry;
  if (typeof provider !== "string" || !provider || typeof name !== "string" || !name) {
    throw new Error(`${where} needs \`provider\` and \`name\``);
  }
  if (entry.base_url === undefined || entry.base_url === null) {
    if (entry.api_key_env !== undefined) {
      throw new Error(`${where}.api_key_env needs base_url; a catalog provider reads its own credentials`);
    }
    return { provider: PROVIDER_ALIASES[provider] ?? provider, name };
  }
  const { base_url: baseUrl, api_key_env: apiKeyEnv } = entry;
  if (typeof baseUrl !== "string" || !/^(env:[A-Za-z_][A-Za-z0-9_]*|https?:\/\/\S+)$/.test(baseUrl)) {
    throw new Error(`${where}.base_url must be env:NAME or an http(s) URL`);
  }
  if (typeof apiKeyEnv !== "string" || !ENV_NAME.test(apiKeyEnv)) {
    throw new Error(`${where}.api_key_env must name the variable holding the endpoint's token`);
  }
  if (provider !== SYSTEM_ONE_PROVIDER_PREFIX && !provider.startsWith(`${SYSTEM_ONE_PROVIDER_PREFIX}-`)) {
    throw new Error(
      `${where}.provider must be ${SYSTEM_ONE_PROVIDER_PREFIX} or start with ${SYSTEM_ONE_PROVIDER_PREFIX}- when base_url is set`,
    );
  }
  return { provider, name, endpoint: { baseUrl, apiKeyEnv } };
}

/**
 * The pi provider serving a configured System One endpoint through pi-ai's
 * `typesafe-system-one` API, which posts to `<base_url>/systemone` with
 * `Authorization: Bearer <token>` and the body `{ model, state, questions }`.
 *
 * Like chat.yaml's compatible endpoints, a base URL from
 * `env:CLASSIFIER_BASE_URL` or `env:CLASSIFIER_BASE_URL_<SUFFIX>` also gets the shared Cloudflare Access
 * token when CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET are set (see
 * models-config.ts); a literal URL never does. The token and Access values are
 * read for each request; while one is missing auth does not resolve and the
 * classification ends with an error. Throws when the base URL does not
 * resolve or only half of the Access token is set.
 */
export function classifierEndpointProvider(
  config: ClassifierModelConfig & { endpoint: ClassifierEndpoint },
  env: NodeJS.ProcessEnv = process.env,
): Provider {
  const { endpoint } = config;
  const baseUrl = resolveBaseUrl(endpoint.baseUrl, env)?.trim();
  if (!baseUrl) throw new Error(`base_url ${endpoint.baseUrl} does not resolve`);
  if (!/^https?:\/\//.test(baseUrl)) throw new Error(`base_url ${endpoint.baseUrl} must resolve to an http(s) URL`);
  const access = usesCloudflareAccess(endpoint.baseUrl, env, CLASSIFIER_ACCESS_VARIABLES);
  const model: ClassifierModel<"typesafe-system-one"> = {
    type: "classifier",
    id: config.name,
    name: config.name,
    api: "typesafe-system-one",
    provider: config.provider,
    baseUrl,
    // Text only: QDash's classifiers are never sent images.
    input: ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 32_768,
  };
  const variables = [endpoint.apiKeyEnv, ...(access ? [CF_ACCESS_ENV.clientId, CF_ACCESS_ENV.clientSecret] : [])];
  return createProvider({
    id: config.provider,
    name: `QDash classifier (${config.provider})`,
    auth: {
      apiKey: {
        name: endpoint.apiKeyEnv,
        // Only the environment, as models.json `$NAME` references: a stored
        // credential for this id is not consulted.
        resolve: async ({ ctx }) => {
          const values = await Promise.all(variables.map(async (name) => (await ctx.env(name))?.trim()));
          if (values.some((value) => !value)) return undefined;
          const [apiKey, clientId, clientSecret] = values as string[];
          return {
            auth: {
              apiKey,
              ...(access
                ? { headers: { "CF-Access-Client-Id": clientId, "CF-Access-Client-Secret": clientSecret } }
                : {}),
            },
            source: variables.join(", "),
          };
        },
      },
    },
    models: [model],
    classifiers: { "typesafe-system-one": typesafeSystemOneApi() },
  });
}

/** Which of the endpoint's variables are unset, for a startup message; never their values. */
export function missingEndpointVariables(endpoint: ClassifierEndpoint, env: NodeJS.ProcessEnv = process.env): string[] {
  const names = [
    ...(endpoint.baseUrl.startsWith("env:") ? [endpoint.baseUrl.slice(4)] : []),
    endpoint.apiKeyEnv,
  ];
  return names.filter((name) => !env[name]?.trim());
}

/** The parts of pi's ModelRuntime that set up classifiers. */
export interface ClassifierRuntime {
  getProvider(providerId: string): unknown;
  registerNativeProvider(provider: Provider): void;
  getModelOfType(type: "classifier", providerId: string, modelId: string): unknown;
  hasConfiguredAuth(providerId: string): boolean;
}

export type Log = Pick<Console, "log" | "warn" | "error">;

/** The declared classifier models and which of them are ready to use. */
export interface ClassifierModels {
  /** Every valid entry of `classifier_models`, in order; the first is the default. */
  declared: readonly ClassifierModelConfig[];
  /** Why a declared model cannot be used, by `provider/name`; absent when it can. */
  unavailable: ReadonlyMap<string, string>;
  /** Set when classifier.yaml itself is invalid; then nothing is declared. */
  error?: string;
}

/**
 * Read classifier.yaml and prepare each model on the runtime: register every
 * System One endpoint as its own provider, and check every catalog
 * classifier and its credentials. Never throws and never stops the chat: an
 * invalid file or an unusable model is logged and reported in the result.
 * Never replaces a provider pi or models.json already has, and never logs a
 * variable's value.
 */
export function configureClassifierModels(
  classifierYaml: string | undefined,
  runtime: ClassifierRuntime,
  env: NodeJS.ProcessEnv,
  log: Log,
): ClassifierModels {
  let declared: ClassifierModelConfig[];
  try {
    declared = classifierModelsFrom(classifierYaml);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    log.error(`[agent-runtime] classifier.yaml ignored: ${message}`);
    return { declared: [], unavailable: new Map(), error: message };
  }
  const unavailable = new Map<string, string>();
  for (const model of declared) {
    const label = classifierLabel(model);
    const reason = prepare(model, runtime, env);
    if (reason) {
      unavailable.set(label, reason);
      log.warn(`[agent-runtime] classifier ${label} unavailable: ${reason}`);
    } else {
      log.log(`[agent-runtime] classifier ${label}${model.endpoint ? " (System One endpoint)" : ""} ready`);
    }
  }
  return { declared, unavailable };
}

function prepare(model: ClassifierModelConfig, runtime: ClassifierRuntime, env: NodeJS.ProcessEnv): string | undefined {
  if (!model.endpoint) {
    if (!runtime.getModelOfType("classifier", model.provider, model.name)) return "not in the model catalog";
    if (!runtime.hasConfiguredAuth(model.provider)) return `no credentials for ${model.provider}`;
    return undefined;
  }
  const missing = missingEndpointVariables(model.endpoint, env);
  if (missing.length > 0) return `${missing.join(", ")} not set`;
  if (runtime.getProvider(model.provider)) {
    return `provider "${model.provider}" already exists; give the endpoint its own provider id`;
  }
  try {
    runtime.registerNativeProvider(classifierEndpointProvider({ ...model, endpoint: model.endpoint }, env));
  } catch (error) {
    return error instanceof Error ? error.message : String(error);
  }
  return undefined;
}

/**
 * The model a feature uses: the one it names, or the first declared. An error
 * message instead when that model is not declared or not usable.
 */
export function selectClassifierModel(
  models: ClassifierModels,
  selection?: Pick<ClassifierModelConfig, "provider" | "name">,
): { model: ClassifierModelConfig } | { error: string } {
  if (models.error) return { error: `classifier.yaml is invalid: ${models.error}` };
  const wanted = selection
    ? { ...selection, provider: PROVIDER_ALIASES[selection.provider] ?? selection.provider }
    : undefined;
  const model = wanted
    ? models.declared.find((m) => m.provider === wanted.provider && m.name === wanted.name)
    : models.declared[0];
  if (!model) {
    return {
      error: wanted
        ? `classifier ${classifierLabel(wanted)} is not in classifier.yaml's classifier_models`
        : "classifier.yaml declares no classifier_models",
    };
  }
  const reason = models.unavailable.get(classifierLabel(model));
  return reason ? { error: `classifier ${classifierLabel(model)} unavailable: ${reason}` } : { model };
}

/** The file's text, or undefined when it does not exist: classifier.yaml is optional. */
export function readClassifierConfig(path: string): string | undefined {
  return existsSync(path) ? readFileSync(path, "utf8") : undefined;
}
