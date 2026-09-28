import { readFileSync, writeFileSync } from "node:fs";

import { parse } from "yaml";

/**
 * Build pi's models.json from QDash's chat.yaml.
 *
 * chat.yaml is the single place model wiring is declared; this module is the
 * only translation into pi's schema. See adr/0004.
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
}

interface ModelEntry {
  id: string;
  contextWindow: number;
  maxTokens: number;
  samplingParams?: Record<string, number>;
}

interface ModelOverride {
  maxTokens?: number;
  samplingParams?: Record<string, number>;
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

/**
 * Translate chat.yaml's `chat_models` into a models.json object.
 *
 * Models with a `base_url` describe an endpoint pi has no catalog for
 * (ollama, vllm, gateways), so they become full provider definitions. Models
 * without one are served by pi's bundled catalog (openai, bedrock); only their
 * sampling parameters are layered on via `modelOverrides`.
 */
export function buildModelsConfig(chatYaml: string, env: NodeJS.ProcessEnv): ModelsConfig {
  const raw = parse(chatYaml) as { chat_models?: unknown } | null;
  const chatModels = Array.isArray(raw?.chat_models) ? (raw.chat_models as ChatModel[]) : [];
  const providers: Record<string, ProviderEntry> = {};

  for (const model of chatModels) {
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
    (entry.models ??= []).push({
      id: name,
      contextWindow: asNumber(model.num_ctx) ?? DEFAULT_CONTEXT_WINDOW,
      maxTokens: maxTokens ?? DEFAULT_MAX_TOKENS,
      ...(sampling ? { samplingParams: sampling } : {}),
    });
  }

  return { providers };
}

/** Generate models.json next to the agent dir and return its path. */
export function writeModelsConfig(chatConfigPath: string, outPath: string): string {
  const config = buildModelsConfig(readFileSync(chatConfigPath, "utf8"), process.env);
  writeFileSync(outPath, `${JSON.stringify(config, null, 2)}\n`);
  return outPath;
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

function samplingParams(model: ChatModel): Record<string, number> | undefined {
  const params: Record<string, number> = {};
  const temperature = asNumber(model.temperature);
  const topP = asNumber(model.top_p);
  const topK = asNumber(model.top_k);
  if (temperature !== undefined) params.temperature = temperature;
  if (topP !== undefined) params.top_p = topP;
  if (topK !== undefined) params.top_k = topK;
  return Object.keys(params).length > 0 ? params : undefined;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}
