import { createStoredChoice } from "@/lib/storedChoice";

export interface ModelOverride {
  provider: string;
  name: string;
  temperature?: number | null;
  max_output_tokens?: number;
  base_url?: string | null;
  api_key_env?: string | null;
  api_style?: string;
  reasoning_effort?: string | null;
}

export interface ModelOption {
  key: string;
  /** The model's name as the menus show it. */
  label: string;
  /** The per-request override to send; null leaves the server's default in force. */
  model: ModelOverride | null;
  isConfiguredDefault?: boolean;
  /** The model this option runs, also for the default option when the config names it. */
  resolvedModel?: ModelOverride | null;
  /** The configured reasoning effort of the model this option runs, for the thinking menu. */
  reasoningEffort?: string | null;
}

const DEFAULT_CHAT_MODEL_KEY = "default";
const NO_CHAT_MODEL_LABEL = "No chat model available";
const CHAT_MODEL_KEY_PREFIX = "model:";

const CHAT_MODEL_STORAGE_KEY = "qdash_chat_model_key";

function readModel(value: unknown): ModelOverride | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (typeof raw.provider !== "string" || typeof raw.name !== "string") {
    return null;
  }
  return {
    provider: raw.provider,
    name: raw.name,
    temperature:
      typeof raw.temperature === "number" || raw.temperature === null ? raw.temperature : undefined,
    max_output_tokens:
      typeof raw.max_output_tokens === "number" ? raw.max_output_tokens : undefined,
    base_url: typeof raw.base_url === "string" || raw.base_url === null ? raw.base_url : undefined,
    api_key_env:
      typeof raw.api_key_env === "string" || raw.api_key_env === null ? raw.api_key_env : undefined,
    api_style: typeof raw.api_style === "string" ? raw.api_style : undefined,
    reasoning_effort:
      typeof raw.reasoning_effort === "string" || raw.reasoning_effort === null
        ? raw.reasoning_effort
        : undefined,
  };
}

/** The `provider:name` of a model, as stored choices name it. */
export function modelIdentity(model: ModelOverride): string {
  return `${model.provider}:${model.name}`;
}

/** The stored key of a chat model: its identity, so a reordered config keeps the choice. */
function chatModelKey(model: ModelOverride): string {
  return `${CHAT_MODEL_KEY_PREFIX}${modelIdentity(model)}`;
}

/** The `provider:name` a stored model key names, or null for the default and legacy keys. */
export function chatModelIdentityOfKey(key: string): string | null {
  return key.startsWith(CHAT_MODEL_KEY_PREFIX) ? key.slice(CHAT_MODEL_KEY_PREFIX.length) : null;
}

/**
 * The chat models a user can pick, default first. The default option sends no
 * override, so the server's `chat_models[0]` answers; it is labelled with that
 * model's name once the config is known. The server lists only models whose API
 * key the agent runtime has, so a config with none left yields a lone default
 * option without a model (see `hasNoChatModel`).
 */
export function buildChatModelOptions(config: Record<string, unknown> | null): ModelOption[] {
  const chatModels = config && Array.isArray(config.chat_models) ? config.chat_models : [];
  const configuredModel = config ? (readModel(chatModels[0]) ?? readModel(config.model)) : null;
  const options: ModelOption[] = [
    {
      key: DEFAULT_CHAT_MODEL_KEY,
      label: configuredModel?.name ?? (config ? NO_CHAT_MODEL_LABEL : "Configured default"),
      model: null,
      isConfiguredDefault: true,
      resolvedModel: configuredModel,
      reasoningEffort: configuredModel?.reasoning_effort ?? null,
    },
  ];
  const seen = new Set<string>();
  if (configuredModel) {
    seen.add(modelIdentity(configuredModel));
  }

  const addOption = (value: unknown) => {
    const model = readModel(value);
    if (!model) return;
    const identity = modelIdentity(model);
    if (seen.has(identity)) return;
    seen.add(identity);
    options.push({
      key: chatModelKey(model),
      label: model.name,
      model,
      resolvedModel: model,
      reasoningEffort: model.reasoning_effort ?? null,
    });
  };

  chatModels.forEach(addOption);
  if (config) addOption(config.model);

  return options;
}

/** Configured models that can judge calibration figures, in configuration order. */
export function buildEvaluationModelOptions(config: Record<string, unknown> | null): ModelOption[] {
  const values = config && Array.isArray(config.evaluation_models) ? config.evaluation_models : [];
  const seen = new Set<string>();
  const options: ModelOption[] = [];
  for (const value of values) {
    const model = readModel(value);
    if (!model) continue;
    const identity = modelIdentity(model);
    if (seen.has(identity)) continue;
    seen.add(identity);
    options.push({
      key: `evaluation-${identity}`,
      label: model.name,
      model,
      reasoningEffort: model.reasoning_effort ?? null,
    });
  }
  return options;
}

/** The remembered chat model, shared by Settings and every chat surface. */
export const chatModelChoice = createStoredChoice<string>(
  CHAT_MODEL_STORAGE_KEY,
  (raw) => raw || DEFAULT_CHAT_MODEL_KEY,
);

export function resolveChatModelOption(options: ModelOption[], key: string): ModelOption {
  return (
    options.find((option) => option.key === key) ??
    options.find((option) => option.isConfiguredDefault) ??
    options[0]
  );
}

/** Whether a loaded config offers no chat model at all: none has its API key set. */
export function hasNoChatModel(options: ModelOption[]): boolean {
  return (
    options.length === 1 && options[0].isConfiguredDefault === true && !options[0].resolvedModel
  );
}
