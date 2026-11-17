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
  /** A remembered model that cannot run now; chats with it fail instead of switching models. */
  unavailable?: boolean;
}

/**
 * The provider of a user's own ChatGPT plan. Its models come from the user's
 * connection in Settings, not from chat.yaml, and the server runs them only
 * with that user's ChatGPT sign-in.
 */
const CHATGPT_PROVIDER = "chatgpt";
export const CHATGPT_USAGE_URL = "https://chatgpt.com/settings/usage";

/** A model the user's connected ChatGPT account offers. */
export interface PlanModel {
  slug: string;
  display_name: string;
  supported?: boolean;
}

const DEFAULT_CHAT_MODEL_KEY = "default";
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

function modelIdentity(model: ModelOverride): string {
  return `${model.provider}:${model.name}`;
}

/** The stored key of a chat model: its identity, so a reordered config keeps the choice. */
function chatModelKey(model: ModelOverride): string {
  return `${CHAT_MODEL_KEY_PREFIX}${modelIdentity(model)}`;
}

/** Whether a model runs on the user's own ChatGPT plan. */
export function isPlanModel(model: ModelOverride | null | undefined): boolean {
  return model?.provider === CHATGPT_PROVIDER;
}

/** How menus name a model's provider. */
export function providerLabel(provider: string | null | undefined): string | undefined {
  if (!provider) return undefined;
  return provider === CHATGPT_PROVIDER ? "ChatGPT plan" : provider;
}

/** Menu options for the models the user's ChatGPT connection can run in chat. */
export function buildPlanModelOptions(models: readonly PlanModel[]): ModelOption[] {
  return models
    .filter((model) => model.supported !== false && model.slug)
    .map((model) => {
      const override: ModelOverride = { provider: CHATGPT_PROVIDER, name: model.slug };
      return {
        key: chatModelKey(override),
        label: model.display_name || model.slug,
        model: override,
        resolvedModel: override,
        reasoningEffort: null,
      };
    });
}

/**
 * A remembered ChatGPT model the connection no longer offers. It stays
 * selected, so the next message fails with a reason instead of silently going
 * to another model or another billing path.
 */
export function unavailablePlanOption(key: string): ModelOption | null {
  const identity = chatModelIdentityOfKey(key);
  const prefix = `${CHATGPT_PROVIDER}:`;
  if (!identity?.startsWith(prefix)) return null;
  const name = identity.slice(prefix.length);
  if (!name) return null;
  const override: ModelOverride = { provider: CHATGPT_PROVIDER, name };
  return {
    key,
    label: `${name} (unavailable)`,
    model: override,
    resolvedModel: override,
    reasoningEffort: null,
    unavailable: true,
  };
}

/** The `provider:name` a stored model key names, or null for the default and legacy keys. */
export function chatModelIdentityOfKey(key: string): string | null {
  return key.startsWith(CHAT_MODEL_KEY_PREFIX) ? key.slice(CHAT_MODEL_KEY_PREFIX.length) : null;
}

/**
 * The chat models a user can pick, default first. The default option sends no
 * override, so the server's `chat_models[0]` answers; it is labelled with that
 * model's name once the config is known.
 */
export function buildChatModelOptions(config: Record<string, unknown> | null): ModelOption[] {
  const chatModels = config && Array.isArray(config.chat_models) ? config.chat_models : [];
  const configuredModel = config ? (readModel(chatModels[0]) ?? readModel(config.model)) : null;
  const options: ModelOption[] = [
    {
      key: DEFAULT_CHAT_MODEL_KEY,
      label: configuredModel?.name ?? "Configured default",
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
