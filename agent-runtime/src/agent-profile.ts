import { readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, join, relative, isAbsolute } from "node:path";

import { parse } from "yaml";

/**
 * Deployment-specific Agent model profiles.
 *
 * `QDASH_AGENT_PROFILE` selects which chat.yaml and evaluation.yaml the
 * runtime builds models.json from. Unset or empty keeps
 * config/agent/chat.yaml and evaluation.yaml. A name selects
 * config/agent/profiles/<name>/chat.yaml and evaluation.yaml, which must both
 * exist and be valid: a named profile never falls back to the default files.
 * config.yaml and classifier.yaml are shared by every profile. Each model
 * entry of a profile is checked field by field (validateAgentProfileDocument);
 * the default files keep their lenient loading.
 *
 * The API applies the same rules in src/qdash/common/config/agent_profile.py;
 * keep the two in step.
 *
 * The pre-rename names QDASH_COPILOT_PROFILE, COPILOT_CONFIG_PATH and a
 * config/copilot directory are still accepted for now (renamedEnvValue,
 * resolveAgentConfigPaths).
 */

export const AGENT_PROFILE_ENV = "QDASH_AGENT_PROFILE";
/** Name of AGENT_PROFILE_ENV before the Copilot -> Agent rename, accepted temporarily. */
export const LEGACY_AGENT_PROFILE_ENV = "QDASH_COPILOT_PROFILE";
export const AGENT_CONFIG_PATH_ENV = "AGENT_CONFIG_PATH";
/** Name of AGENT_CONFIG_PATH_ENV before the Copilot -> Agent rename, accepted temporarily. */
export const LEGACY_AGENT_CONFIG_PATH_ENV = "COPILOT_CONFIG_PATH";
export const AGENT_CONFIG_DIRNAME = "agent";
/** Name of config/agent before the Copilot -> Agent rename, read as a fallback. */
export const LEGACY_AGENT_CONFIG_DIRNAME = "copilot";
export const PROFILES_DIRNAME = "profiles";
/** Lowercase letters, digits, `-` and `_`; no separators or dots. */
export const PROFILE_NAME_PATTERN = /^[a-z0-9][a-z0-9_-]{0,62}$/;

type ProfileFileKind = "chat" | "evaluation";

/** The one top-level key each profile file may set. */
const PROFILE_FILE_KEYS: Record<ProfileFileKind, string> = {
  chat: "chat_models",
  evaluation: "evaluation_models",
};

export class AgentProfileError extends Error {
  override name = "AgentProfileError";
}

/** The model files the runtime reads, and the profile they belong to. */
export interface AgentModelFiles {
  /** The selected profile; undefined for the default files. */
  profile?: string;
  chatPath: string;
  evaluationPath: string;
}

/** The model YAML a runtime builds models.json and compaction budgets from. */
export interface AgentModelYaml {
  chatYaml: string;
  evaluationYaml: string | undefined;
}

/**
 * The value of a renamed variable and the name it was read from.
 *
 * Undefined when neither name is set. When only one is set, its value is used,
 * empty or not. When both are set, equal values are fine and an empty value
 * gives way to a non-empty one; two different non-empty values are an error,
 * so a stale legacy line cannot silently win or lose. The API applies the same
 * rules in `renamed_env_value`.
 */
export function renamedEnvValue(
  env: NodeJS.ProcessEnv,
  name: string,
  legacy: string,
): { name: string; value: string } | undefined {
  const current = env[name];
  const old = env[legacy];
  if (old === undefined) return current === undefined ? undefined : { name, value: current };
  if (current === undefined || (current === "" && old !== "")) return { name: legacy, value: old };
  if (old !== "" && old !== current) {
    throw new AgentProfileError(
      `${name}=${JSON.stringify(current)} conflicts with the legacy ${legacy}=${JSON.stringify(old)}; set only ${name}`,
    );
  }
  return { name, value: current };
}

/**
 * The validated profile name, or undefined when the variable is unset or empty.
 *
 * An empty value means the default files, as an empty `KEY=` line in a Compose
 * `env_file` passes an empty string. Surrounding whitespace is not stripped.
 * QDASH_COPILOT_PROFILE is read as a legacy alias (see renamedEnvValue).
 */
export function selectedAgentProfile(
  env: NodeJS.ProcessEnv,
  warn: (message: string) => void = console.warn,
): string | undefined {
  const selected = renamedEnvValue(env, AGENT_PROFILE_ENV, LEGACY_AGENT_PROFILE_ENV);
  if (selected === undefined || selected.value === "") return undefined;
  const { name: source, value: name } = selected;
  if (source === LEGACY_AGENT_PROFILE_ENV) {
    warn(`${source} is deprecated; rename it to ${AGENT_PROFILE_ENV}`);
  }
  if (!PROFILE_NAME_PATTERN.test(name)) {
    throw new AgentProfileError(
      `${source}=${JSON.stringify(name)} is not a valid profile name: use 1-63 lowercase letters, digits, '-' or '_', starting with a letter or digit`,
    );
  }
  return name;
}

/** The Agent config.yaml and classifier.yaml a runtime reads. */
export interface AgentConfigPaths {
  configPath: string;
  classifierPath: string;
}

/**
 * Where config.yaml and classifier.yaml are.
 *
 * AGENT_CONFIG_PATH (or the legacy COPILOT_CONFIG_PATH) names config.yaml;
 * unset or empty means `<configRoot>/agent/config.yaml`. CLASSIFIER_CONFIG_PATH
 * names classifier.yaml; unset means `<configRoot>/agent/classifier.yaml`.
 * A configuration root that has only the pre-rename `copilot/` directory is
 * read from there, with a warning. A path given in a variable is used as is.
 * The API resolves config.yaml the same way in `resolve_agent_config_path`.
 */
export function resolveAgentConfigPaths(
  env: NodeJS.ProcessEnv,
  configRoot: string,
  warn: (message: string) => void = console.warn,
): AgentConfigPaths {
  const explicit = renamedEnvValue(env, AGENT_CONFIG_PATH_ENV, LEGACY_AGENT_CONFIG_PATH_ENV);
  if (explicit?.name === LEGACY_AGENT_CONFIG_PATH_ENV && explicit.value !== "") {
    warn(`${LEGACY_AGENT_CONFIG_PATH_ENV} is deprecated; rename it to ${AGENT_CONFIG_PATH_ENV}`);
  }
  const needsDefault = !explicit?.value || env.CLASSIFIER_CONFIG_PATH === undefined;
  const defaultDir = needsDefault ? defaultAgentConfigDir(configRoot, warn) : "";
  return {
    configPath: explicit?.value || join(defaultDir, "config.yaml"),
    classifierPath: env.CLASSIFIER_CONFIG_PATH ?? join(defaultDir, "classifier.yaml"),
  };
}

/** `<configRoot>/agent`, or a legacy `<configRoot>/copilot` when only that exists. */
function defaultAgentConfigDir(configRoot: string, warn: (message: string) => void): string {
  const agentDir = join(configRoot, AGENT_CONFIG_DIRNAME);
  const legacyDir = join(configRoot, LEGACY_AGENT_CONFIG_DIRNAME);
  if (!exists(agentDir) && isDirectory(legacyDir)) {
    warn(`${legacyDir} is deprecated; rename it to ${agentDir}`);
    return legacyDir;
  }
  return agentDir;
}

/**
 * Where the chat and evaluation models come from.
 *
 * `agentConfigPath` is config/agent/config.yaml; profiles live next to it.
 * The `CHAT_CONFIG_PATH` and `EVALUATION_CONFIG_PATH` overrides apply to the
 * default files only, and conflict with a named profile; unset or empty means
 * the file next to config.yaml. The API applies the same rules in
 * `resolve_agent_model_files`.
 */
export function resolveAgentModelFiles(
  env: NodeJS.ProcessEnv,
  agentConfigPath: string,
): AgentModelFiles {
  const agentDir = dirname(agentConfigPath);
  const profile = selectedAgentProfile(env);
  if (profile === undefined) {
    return {
      chatPath: env.CHAT_CONFIG_PATH || join(agentDir, "chat.yaml"),
      evaluationPath: env.EVALUATION_CONFIG_PATH || join(agentDir, "evaluation.yaml"),
    };
  }
  const overrides = ["CHAT_CONFIG_PATH", "EVALUATION_CONFIG_PATH"].filter((name) => env[name]);
  if (overrides.length > 0) {
    throw new AgentProfileError(
      `${AGENT_PROFILE_ENV}=${profile} conflicts with ${overrides.join(" and ")}; set one or the other`,
    );
  }
  const files = agentProfileFiles(agentDir, profile);
  return { profile, chatPath: files.chat, evaluationPath: files.evaluation };
}

/** The chat and evaluation files of a profile, which must exist inside its directory. */
export function agentProfileFiles(
  agentDir: string,
  profile: string,
): Record<ProfileFileKind, string> {
  if (!PROFILE_NAME_PATTERN.test(profile)) {
    throw new AgentProfileError(`invalid Agent profile name ${JSON.stringify(profile)}`);
  }
  const profileDir = join(agentDir, PROFILES_DIRNAME, profile);
  if (!isDirectory(profileDir)) {
    // A profile added under the pre-rename config/copilot is not read from there.
    const legacyDir = join(dirname(agentDir), LEGACY_AGENT_CONFIG_DIRNAME, PROFILES_DIRNAME, profile);
    const hint = isDirectory(legacyDir) ? `; move ${legacyDir} there` : "";
    throw new AgentProfileError(
      `Agent profile ${JSON.stringify(profile)} not found: ${profileDir} is not a directory (set by ${AGENT_PROFILE_ENV})${hint}`,
    );
  }
  const profilesRoot = realpathSync(join(agentDir, PROFILES_DIRNAME));
  const files = {} as Record<ProfileFileKind, string>;
  for (const kind of Object.keys(PROFILE_FILE_KEYS) as ProfileFileKind[]) {
    const path = join(profileDir, `${kind}.yaml`);
    if (!isFile(path)) {
      throw new AgentProfileError(
        `Agent profile ${JSON.stringify(profile)} is missing ${path}; a profile needs both chat.yaml and evaluation.yaml`,
      );
    }
    // A symlinked profile directory or file must still resolve under profiles/.
    const inside = relative(profilesRoot, realpathSync(path));
    if (inside === "" || inside.startsWith("..") || isAbsolute(inside)) {
      throw new AgentProfileError(
        `Agent profile ${JSON.stringify(profile)}: ${path} resolves outside ${profilesRoot}`,
      );
    }
    files[kind] = path;
  }
  return files;
}

/**
 * Read the model YAML of the selected files.
 *
 * The default files keep their historic tolerance: a missing evaluation.yaml
 * is ignored with a warning. A profile's files are required and validated.
 */
export function readAgentModelYaml(files: AgentModelFiles): AgentModelYaml {
  if (files.profile === undefined) {
    return {
      chatYaml: readFileSync(files.chatPath, "utf8"),
      evaluationYaml: readFileIfPresent(files.evaluationPath),
    };
  }
  return {
    chatYaml: readProfileFile("chat", files.chatPath),
    evaluationYaml: readProfileFile("evaluation", files.evaluationPath),
  };
}

function readProfileFile(kind: ProfileFileKind, path: string): string {
  let text: string;
  let data: unknown;
  try {
    text = readFileSync(path, "utf8");
    data = parse(text);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new AgentProfileError(`cannot read Agent profile file ${path}: ${reason}`);
  }
  validateAgentProfileDocument(kind, data, path);
  return text;
}

/**
 * Every key a profile model entry may set: the fields of the API's ModelConfig
 * and the keys only models.json generation reads.
 */
export const PROFILE_MODEL_FIELDS: readonly string[] = [
  "provider",
  "name",
  "temperature",
  "max_output_tokens",
  "base_url",
  "api_key_env",
  "keep_alive",
  "num_ctx",
  "top_p",
  "top_k",
  "sampling_params",
  "sampling_params_by_thinking_level",
  "reasoning_effort",
  "disable_thinking_instruction",
  "api_style",
  "strict_tool_schemas",
  "prompt_cache_key_mode",
  "requires_non_null_assistant_content",
  "requires_tools_with_tool_history",
];

const API_STYLES = ["responses", "completion"];
const REASONING_EFFORTS = ["none", "minimal", "low", "medium", "high"];
const THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "max"];
const PROMPT_CACHE_KEY_MODES = ["auto", "enabled", "disabled"];
/** Keys written as compat of a custom endpoint; catalog models ignore them. */
const BASE_URL_ONLY_FIELDS = [
  "strict_tool_schemas",
  "prompt_cache_key_mode",
  "requires_non_null_assistant_content",
  "requires_tools_with_tool_history",
];
const COMPLETION_ONLY_FIELDS = [
  "requires_non_null_assistant_content",
  "requires_tools_with_tool_history",
];
const NULLABLE_FIELDS = new Set([
  "temperature",
  "base_url",
  "api_key_env",
  "keep_alive",
  "num_ctx",
  "top_p",
  "top_k",
  "reasoning_effort",
]);
const BOOLEAN_FIELDS = new Set([
  "disable_thinking_instruction",
  "strict_tool_schemas",
  "requires_non_null_assistant_content",
  "requires_tools_with_tool_history",
]);
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Why one field's value is not accepted, or undefined. Mirrors `_model_field_error`. */
function modelFieldError(field: string, value: unknown): string | undefined {
  if (value === null) return NULLABLE_FIELDS.has(field) ? undefined : "must not be null";
  const oneOf = (allowed: string[]) =>
    allowed.includes(value as string) ? undefined : `must be one of ${allowed.join(", ")}`;
  switch (field) {
    case "provider":
    case "name":
    case "keep_alive":
      return typeof value === "string" && value !== "" ? undefined : "must be a non-empty string";
    case "api_style":
      return oneOf(API_STYLES);
    case "base_url":
      if (typeof value === "string") {
        if (value.startsWith("env:") && ENV_NAME.test(value.slice(4))) return undefined;
        if (/^https?:\/\/./.test(value)) return undefined;
      }
      return "must be an http:// or https:// URL or env:NAME";
    case "api_key_env":
      return typeof value === "string" && ENV_NAME.test(value)
        ? undefined
        : "must be an environment variable name";
    case "temperature":
      if (!isFiniteNumber(value)) return "must be a finite number";
      return value >= 0 ? undefined : "must be at least 0";
    case "top_p":
      if (!isFiniteNumber(value)) return "must be a finite number";
      return value > 0 && value <= 1 ? undefined : "must be greater than 0 and at most 1";
    case "max_output_tokens":
    case "num_ctx":
      if (!Number.isSafeInteger(value)) return "must be a whole number";
      return (value as number) >= 1 ? undefined : "must be at least 1";
    case "top_k":
      if (!Number.isSafeInteger(value)) return "must be a whole number";
      return (value as number) >= -1 ? undefined : "must be at least -1";
    case "reasoning_effort":
      return oneOf(REASONING_EFFORTS);
    case "prompt_cache_key_mode":
      return oneOf(PROMPT_CACHE_KEY_MODES);
    case "sampling_params":
      return isRecord(value) ? undefined : "must be a mapping";
    case "sampling_params_by_thinking_level": {
      if (!isRecord(value)) return "must be a mapping";
      const unknown = Object.keys(value).filter((level) => !THINKING_LEVELS.includes(level)).sort();
      if (unknown.length > 0) {
        return `has unknown level(s) ${unknown.join(", ")}; use ${THINKING_LEVELS.join(", ")}`;
      }
      for (const [level, params] of Object.entries(value)) {
        if (!isRecord(params)) return `${level} must be a mapping`;
      }
      return undefined;
    }
    default:
      if (BOOLEAN_FIELDS.has(field)) {
        return typeof value === "boolean" ? undefined : "must be true or false";
      }
      return undefined;
  }
}

/** Check one model entry of a profile. Mirrors `_validate_profile_model`. */
function validateProfileModel(where: string, model: Record<string, unknown>): void {
  const unknown = Object.keys(model).filter((field) => !PROFILE_MODEL_FIELDS.includes(field)).sort();
  if (unknown.length > 0) {
    throw new AgentProfileError(
      `${where} has unknown field(s) ${unknown.join(", ")}; see docs/developer-guide/agent/model-configuration.md#deployment-profiles`,
    );
  }
  for (const field of ["provider", "name"]) {
    if (!(field in model)) {
      throw new AgentProfileError(`${where}.${field} must be a non-empty string`);
    }
  }
  for (const field of Object.keys(model).sort()) {
    const error = modelFieldError(field, model[field]);
    if (error !== undefined) throw new AgentProfileError(`${where}.${field} ${error}`);
  }
  const maxOutput = model.max_output_tokens;
  const numCtx = model.num_ctx;
  if (typeof maxOutput === "number" && typeof numCtx === "number" && maxOutput >= numCtx) {
    throw new AgentProfileError(`${where}.max_output_tokens must be less than num_ctx`);
  }
  for (const field of BASE_URL_ONLY_FIELDS) {
    if (field in model && (model.base_url === undefined || model.base_url === null)) {
      throw new AgentProfileError(`${where}.${field} applies only to a model with base_url`);
    }
  }
  if (model.api_style === "responses") {
    for (const field of COMPLETION_ONLY_FIELDS) {
      if (field in model) {
        throw new AgentProfileError(`${where}.${field} applies only to api_style completion`);
      }
    }
  }
}

/**
 * Check a profile file before any model is built from it.
 *
 * The document holds only its one list; each entry is checked field by field
 * and a provider/name pair appears once. Mirrors
 * `validate_agent_profile_document`.
 */
export function validateAgentProfileDocument(
  kind: ProfileFileKind,
  data: unknown,
  path: string,
): void {
  const key = PROFILE_FILE_KEYS[kind];
  if (!isRecord(data)) {
    throw new AgentProfileError(`${path}: expected a mapping with a '${key}' list`);
  }
  const unexpected = Object.keys(data).filter((name) => name !== key).sort();
  if (unexpected.length > 0) {
    throw new AgentProfileError(
      `${path}: unexpected key(s) ${unexpected.join(", ")}; a profile ${kind}.yaml sets only '${key}' (shared settings stay in config/agent/config.yaml)`,
    );
  }
  const models = data[key];
  if (!Array.isArray(models)) {
    throw new AgentProfileError(`${path}: '${key}' must be a list`);
  }
  if (kind === "chat" && models.length === 0) {
    throw new AgentProfileError(`${path}: '${key}' must list at least one model`);
  }
  const seen = new Map<string, number>();
  models.forEach((model, index) => {
    const where = `${path}: ${key}[${index}]`;
    if (!isRecord(model)) {
      throw new AgentProfileError(`${where} must be a mapping`);
    }
    validateProfileModel(where, model);
    const identity = JSON.stringify([model.provider, model.name]);
    const first = seen.get(identity);
    if (first !== undefined) {
      throw new AgentProfileError(`${where} repeats the provider and name of ${key}[${first}]`);
    }
    seen.set(identity, index);
  });
}

function readFileIfPresent(path: string): string | undefined {
  try {
    return readFileSync(path, "utf8");
  } catch (error) {
    console.warn(`[agent-runtime] could not read ${path}, ignoring:`, error);
    return undefined;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exists(path: string): boolean {
  try {
    statSync(path);
    return true;
  } catch {
    return false;
  }
}

function isDirectory(path: string): boolean {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

function isFile(path: string): boolean {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}
