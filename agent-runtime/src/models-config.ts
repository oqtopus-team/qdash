import { readFileSync, writeFileSync } from "node:fs";

import { parse } from "yaml";

/**
 * Build pi's models.json from QDash's chat.yaml and review.yaml.
 *
 * Those two files are the single place model wiring is declared; this module is
 * the only translation into pi's schema. See adr/0004 of the chat session and
 * adr/0001 of 2026-09-28-ai-review-pi-agent.
 */

/** QDash's chat config names providers the way LiteLLM does; pi uses its own ids. */
export const PROVIDER_ALIASES: Record<string, string> = { bedrock: "amazon-bedrock" };

/** Used for locally hosted models, whose context window chat.yaml does not state. */
const DEFAULT_CONTEXT_WINDOW = 131072;
const DEFAULT_MAX_TOKENS = 4096;

interface ChatModel {
  provider?: unknown;
  name?: unknown;
  api_style?: unknown;
  base_url?: unknown;
  api_key_env?: unknown;
  num_ctx?: unknown;
  max_output_tokens?: unknown;
  temperature?: unknown;
  top_p?: unknown;
  top_k?: unknown;
  keep_alive?: unknown;
}

interface ModelEntry {
  id: string;
  contextWindow: number;
  maxTokens: number;
  samplingParams?: Record<string, unknown>;
}

interface ModelOverride {
  maxTokens?: number;
  samplingParams?: Record<string, unknown>;
}

interface ProviderEntry {
  baseUrl?: string;
  api?: string;
  apiKey?: string;
  compat?: Record<string, boolean>;
  models?: ModelEntry[];
  modelOverrides?: Record<string, ModelOverride>;
}

export interface ModelsConfig {
  providers: Record<string, ProviderEntry>;
}

/** Read one model list out of a YAML document, tolerating a missing key. */
function readModels(yaml: string | undefined, key: string): ChatModel[] {
  if (!yaml) return [];
  const raw = parse(yaml) as Record<string, unknown> | null;
  const list = raw?.[key];
  return Array.isArray(list) ? (list as ChatModel[]) : [];
}

/**
 * Translate chat.yaml's `chat_models` and review.yaml's `analysis_models` into a
 * models.json object.
 *
 * Models with a `base_url` describe an endpoint pi has no catalog for
 * (ollama, vllm, gateways), so they become full provider definitions. Models
 * without one are served by pi's bundled catalog (openai, bedrock); only their
 * sampling parameters are layered on via `modelOverrides`.
 *
 * Chat and review routinely name the same provider and sometimes the same
 * model, so entries are merged rather than appended blindly.
 */
export function buildModelsConfig(
  chatYaml: string,
  reviewYaml: string | undefined,
  env: NodeJS.ProcessEnv,
): ModelsConfig {
  const models = [
    ...readModels(chatYaml, "chat_models"),
    ...readModels(reviewYaml, "analysis_models"),
  ];
  const providers: Record<string, ProviderEntry> = {};

  for (const model of models) {
    const name = asString(model.name);
    const rawProvider = asString(model.provider);
    if (!name || !rawProvider) continue;

    const providerId = PROVIDER_ALIASES[rawProvider] ?? rawProvider;
    const baseUrlSetting = asString(model.base_url);
    const sampling = samplingParams(model);
    const maxTokens = asNumber(model.max_output_tokens);

    if (!baseUrlSetting) {
      if (!sampling && maxTokens === undefined) continue;
      const entry = (providers[providerId] ??= {});
      const overrides = (entry.modelOverrides ??= {});
      if (overrides[name]) continue;
      overrides[name] = {
        ...(maxTokens === undefined ? {} : { maxTokens }),
        ...(sampling ? { samplingParams: sampling } : {}),
      };
      continue;
    }

    const baseUrl = resolveBaseUrl(baseUrlSetting, env);
    if (!baseUrl) {
      console.warn(
        `[agent-runtime] skipping ${providerId}/${name}: ${baseUrlSetting} does not resolve`,
      );
      continue;
    }

    const entry = (providers[providerId] ??= {
      baseUrl,
      api: apiFromStyle(asString(model.api_style)),
      // Pi hides models whose provider has no credential, even when the server
      // ignores it, so keyless local endpoints still need a placeholder.
      ...(asString(model.api_key_env) ? { apiKey: `$${asString(model.api_key_env)}` } : {}),
      // Local OpenAI-compatible servers generally implement neither.
      compat: { supportsDeveloperRole: false, supportsReasoningEffort: false },
      models: [],
    });
    const models_ = (entry.models ??= []);
    if (models_.some((existing) => existing.id === name)) continue;
    models_.push({
      id: name,
      contextWindow: asNumber(model.num_ctx) ?? DEFAULT_CONTEXT_WINDOW,
      maxTokens: maxTokens ?? DEFAULT_MAX_TOKENS,
      ...(sampling ? { samplingParams: sampling } : {}),
    });
  }

  return { providers };
}

/** Generate models.json next to the agent dir and return its path. */
export function writeModelsConfig(
  chatConfigPath: string,
  reviewConfigPath: string,
  outPath: string,
): string {
  const config = buildModelsConfig(
    readFileSync(chatConfigPath, "utf8"),
    readFileIfPresent(reviewConfigPath),
    process.env,
  );
  writeFileSync(outPath, `${JSON.stringify(config, null, 2)}\n`);
  return outPath;
}

function readFileIfPresent(path: string): string | undefined {
  try {
    return readFileSync(path, "utf8");
  } catch (error) {
    console.warn(`[agent-runtime] could not read ${path}, ignoring:`, error);
    return undefined;
  }
}

/** `env:NAME` reads the environment; anything else is a literal URL. */
function resolveBaseUrl(setting: string, env: NodeJS.ProcessEnv): string | undefined {
  if (!setting.startsWith("env:")) return setting;
  return env[setting.slice(4)] || undefined;
}

/** Only the /v1/responses style has its own pi api; everything else is completions. */
function apiFromStyle(style: string | undefined): string {
  return style === "responses" ? "openai-responses" : "openai-completions";
}

/**
 * Sampling parameters pi merges into the request body verbatim.
 *
 * `keep_alive` is not a sampling parameter, but ollama reads it from the same
 * body and it keeps the local VLM resident between reviews, so it rides along.
 */
function samplingParams(model: ChatModel): Record<string, unknown> | undefined {
  const params: Record<string, unknown> = {};
  const temperature = asNumber(model.temperature);
  const topP = asNumber(model.top_p);
  const topK = asNumber(model.top_k);
  const keepAlive = asString(model.keep_alive);
  if (temperature !== undefined) params.temperature = temperature;
  if (topP !== undefined) params.top_p = topP;
  if (topK !== undefined) params.top_k = topK;
  if (keepAlive !== undefined) params.keep_alive = keepAlive;
  return Object.keys(params).length > 0 ? params : undefined;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}
