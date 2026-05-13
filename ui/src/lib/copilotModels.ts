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

interface ModelOption {
  key: string;
  label: string;
  model: ModelOverride | null;
  isConfiguredDefault?: boolean;
}

const ANALYSIS_MODEL_STORAGE_KEY = "qdash_analysis_model_key";
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

export function buildAnalysisModelOptions(config: Record<string, unknown> | null): ModelOption[] {
  if (!config) {
    return [
      {
        key: "default",
        label: "Configured model",
        model: null,
        isConfiguredDefault: true,
      },
    ];
  }

  const analysisModels = Array.isArray(config.analysis_models) ? config.analysis_models : [];
  const configuredModel =
    readModel(analysisModels[0]) ?? readModel(config.analysis_model) ?? readModel(config.model);
  const options: ModelOption[] = [
    {
      key: "default",
      label: configuredModel ? `Configured: ${configuredModel.name}` : "Configured model",
      model: null,
      isConfiguredDefault: true,
    },
  ];
  const seen = new Set<string>();
  if (configuredModel) {
    seen.add(modelIdentity(configuredModel));
  }

  const addOption = (key: string, label: string, value: unknown) => {
    const model = readModel(value);
    if (!model) return;
    const identity = modelIdentity(model);
    if (seen.has(identity)) return;
    seen.add(identity);
    options.push({
      key,
      label: `${label}: ${model.name}`,
      model,
    });
  };

  analysisModels.forEach((model, index) => {
    addOption(`analysis-${index}`, `Analysis ${index + 1}`, model);
  });
  addOption("legacy-analysis", "Analysis", config.analysis_model);
  addOption("general", "General", config.model);

  return options;
}

export function getStoredAnalysisModelKey(): string {
  if (typeof window === "undefined") return "default";
  return localStorage.getItem(ANALYSIS_MODEL_STORAGE_KEY) || "default";
}

export function setStoredAnalysisModelKey(key: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ANALYSIS_MODEL_STORAGE_KEY, key);
}

export function resolveAnalysisModelOption(options: ModelOption[], key: string): ModelOption {
  return (
    options.find((option) => option.key === key) ??
    options.find((option) => option.isConfiguredDefault) ??
    options[0]
  );
}

export function buildChatModelOptions(config: Record<string, unknown> | null): ModelOption[] {
  if (!config) {
    return [
      {
        key: "default",
        label: "Configured model",
        model: null,
        isConfiguredDefault: true,
      },
    ];
  }

  const chatModels = Array.isArray(config.chat_models) ? config.chat_models : [];
  const configuredModel = readModel(chatModels[0]) ?? readModel(config.model);
  const options: ModelOption[] = [
    {
      key: "default",
      label: configuredModel ? `Configured: ${configuredModel.name}` : "Configured model",
      model: null,
      isConfiguredDefault: true,
    },
  ];
  const seen = new Set<string>();
  if (configuredModel) {
    seen.add(modelIdentity(configuredModel));
  }

  const addOption = (key: string, label: string, value: unknown) => {
    const model = readModel(value);
    if (!model) return;
    const identity = modelIdentity(model);
    if (seen.has(identity)) return;
    seen.add(identity);
    options.push({
      key,
      label: `${label}: ${model.name}`,
      model,
    });
  };

  chatModels.forEach((model, index) => {
    addOption(`chat-${index}`, `Chat ${index + 1}`, model);
  });
  addOption("general", "General", config.model);

  return options;
}

export function getStoredChatModelKey(): string {
  if (typeof window === "undefined") return "default";
  return localStorage.getItem(CHAT_MODEL_STORAGE_KEY) || "default";
}

export function setStoredChatModelKey(key: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(CHAT_MODEL_STORAGE_KEY, key);
}

export function resolveChatModelOption(options: ModelOption[], key: string): ModelOption {
  return (
    options.find((option) => option.key === key) ??
    options.find((option) => option.isConfiguredDefault) ??
    options[0]
  );
}
