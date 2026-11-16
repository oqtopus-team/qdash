import { readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, join, relative, isAbsolute } from "node:path";

import { parse } from "yaml";

/**
 * Deployment-specific Copilot model profiles.
 *
 * `QDASH_COPILOT_PROFILE` selects which chat.yaml and evaluation.yaml the
 * runtime builds models.json from. Unset or empty keeps
 * config/copilot/chat.yaml and evaluation.yaml. A name selects
 * config/copilot/profiles/<name>/chat.yaml and evaluation.yaml, which must both
 * exist and be valid: a named profile never falls back to the default files.
 * config.yaml and classifier.yaml are shared by every profile. Each model
 * entry of a profile is checked field by field (validateCopilotProfileDocument);
 * the default files keep their lenient loading.
 *
 * The API applies the same rules in src/qdash/common/config/copilot_profile.py;
 * keep the two in step.
 */

export const COPILOT_PROFILE_ENV = "QDASH_COPILOT_PROFILE";
export const PROFILES_DIRNAME = "profiles";
/** Lowercase letters, digits, `-` and `_`; no separators or dots. */
export const PROFILE_NAME_PATTERN = /^[a-z0-9][a-z0-9_-]{0,62}$/;

type ProfileFileKind = "chat" | "evaluation";

/** The one top-level key each profile file may set. */
const PROFILE_FILE_KEYS: Record<ProfileFileKind, string> = {
  chat: "chat_models",
  evaluation: "evaluation_models",
};

export class CopilotProfileError extends Error {
  override name = "CopilotProfileError";
}

/** The model files the runtime reads, and the profile they belong to. */
export interface CopilotModelFiles {
  /** The selected profile; undefined for the default files. */
  profile?: string;
  chatPath: string;
  evaluationPath: string;
}

/** The model YAML a runtime builds models.json and compaction budgets from. */
export interface CopilotModelYaml {
  chatYaml: string;
  evaluationYaml: string | undefined;
}

/**
 * The validated profile name, or undefined when the variable is unset or empty.
 *
 * An empty value means the default files, as an empty `KEY=` line in a Compose
 * `env_file` passes an empty string. Surrounding whitespace is not stripped.
 */
export function selectedCopilotProfile(env: NodeJS.ProcessEnv): string | undefined {
  const name = env[COPILOT_PROFILE_ENV] ?? "";
  if (name === "") return undefined;
  if (!PROFILE_NAME_PATTERN.test(name)) {
    throw new CopilotProfileError(
      `${COPILOT_PROFILE_ENV}=${JSON.stringify(name)} is not a valid profile name: use 1-63 lowercase letters, digits, '-' or '_', starting with a letter or digit`,
    );
  }
  return name;
}

/**
 * Where the chat and evaluation models come from.
 *
 * `copilotConfigPath` is config/copilot/config.yaml; profiles live next to it.
 * The `CHAT_CONFIG_PATH` and `EVALUATION_CONFIG_PATH` overrides apply to the
 * default files only, and conflict with a named profile.
 */
export function resolveCopilotModelFiles(
  env: NodeJS.ProcessEnv,
  copilotConfigPath: string,
): CopilotModelFiles {
  const copilotDir = dirname(copilotConfigPath);
  const profile = selectedCopilotProfile(env);
  if (profile === undefined) {
    return {
      chatPath: env.CHAT_CONFIG_PATH ?? join(copilotDir, "chat.yaml"),
      evaluationPath: env.EVALUATION_CONFIG_PATH ?? join(copilotDir, "evaluation.yaml"),
    };
  }
  const overrides = ["CHAT_CONFIG_PATH", "EVALUATION_CONFIG_PATH"].filter((name) => env[name]);
  if (overrides.length > 0) {
    throw new CopilotProfileError(
      `${COPILOT_PROFILE_ENV}=${profile} conflicts with ${overrides.join(" and ")}; set one or the other`,
    );
  }
  const files = copilotProfileFiles(copilotDir, profile);
  return { profile, chatPath: files.chat, evaluationPath: files.evaluation };
}

/** The chat and evaluation files of a profile, which must exist inside its directory. */
export function copilotProfileFiles(
  copilotDir: string,
  profile: string,
): Record<ProfileFileKind, string> {
  if (!PROFILE_NAME_PATTERN.test(profile)) {
    throw new CopilotProfileError(`invalid Copilot profile name ${JSON.stringify(profile)}`);
  }
  const profileDir = join(copilotDir, PROFILES_DIRNAME, profile);
  if (!isDirectory(profileDir)) {
    throw new CopilotProfileError(
      `Copilot profile ${JSON.stringify(profile)} not found: ${profileDir} is not a directory (set by ${COPILOT_PROFILE_ENV})`,
    );
  }
  const profilesRoot = realpathSync(join(copilotDir, PROFILES_DIRNAME));
  const files = {} as Record<ProfileFileKind, string>;
  for (const kind of Object.keys(PROFILE_FILE_KEYS) as ProfileFileKind[]) {
    const path = join(profileDir, `${kind}.yaml`);
    if (!isFile(path)) {
      throw new CopilotProfileError(
        `Copilot profile ${JSON.stringify(profile)} is missing ${path}; a profile needs both chat.yaml and evaluation.yaml`,
      );
    }
    // A symlinked profile directory or file must still resolve under profiles/.
    const inside = relative(profilesRoot, realpathSync(path));
    if (inside === "" || inside.startsWith("..") || isAbsolute(inside)) {
      throw new CopilotProfileError(
        `Copilot profile ${JSON.stringify(profile)}: ${path} resolves outside ${profilesRoot}`,
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
export function readCopilotModelYaml(files: CopilotModelFiles): CopilotModelYaml {
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
    throw new CopilotProfileError(`cannot read Copilot profile file ${path}: ${reason}`);
  }
  validateCopilotProfileDocument(kind, data, path);
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
    throw new CopilotProfileError(
      `${where} has unknown field(s) ${unknown.join(", ")}; see docs/developer-guide/copilot/model-configuration.md#deployment-profiles`,
    );
  }
  for (const field of ["provider", "name"]) {
    if (!(field in model)) {
      throw new CopilotProfileError(`${where}.${field} must be a non-empty string`);
    }
  }
  for (const field of Object.keys(model).sort()) {
    const error = modelFieldError(field, model[field]);
    if (error !== undefined) throw new CopilotProfileError(`${where}.${field} ${error}`);
  }
  const maxOutput = model.max_output_tokens;
  const numCtx = model.num_ctx;
  if (typeof maxOutput === "number" && typeof numCtx === "number" && maxOutput >= numCtx) {
    throw new CopilotProfileError(`${where}.max_output_tokens must be less than num_ctx`);
  }
  for (const field of BASE_URL_ONLY_FIELDS) {
    if (field in model && (model.base_url === undefined || model.base_url === null)) {
      throw new CopilotProfileError(`${where}.${field} applies only to a model with base_url`);
    }
  }
  if (model.api_style === "responses") {
    for (const field of COMPLETION_ONLY_FIELDS) {
      if (field in model) {
        throw new CopilotProfileError(`${where}.${field} applies only to api_style completion`);
      }
    }
  }
}

/**
 * Check a profile file before any model is built from it.
 *
 * The document holds only its one list; each entry is checked field by field
 * and a provider/name pair appears once. Mirrors
 * `validate_copilot_profile_document`.
 */
export function validateCopilotProfileDocument(
  kind: ProfileFileKind,
  data: unknown,
  path: string,
): void {
  const key = PROFILE_FILE_KEYS[kind];
  if (!isRecord(data)) {
    throw new CopilotProfileError(`${path}: expected a mapping with a '${key}' list`);
  }
  const unexpected = Object.keys(data).filter((name) => name !== key).sort();
  if (unexpected.length > 0) {
    throw new CopilotProfileError(
      `${path}: unexpected key(s) ${unexpected.join(", ")}; a profile ${kind}.yaml sets only '${key}' (shared settings stay in config/copilot/config.yaml)`,
    );
  }
  const models = data[key];
  if (!Array.isArray(models)) {
    throw new CopilotProfileError(`${path}: '${key}' must be a list`);
  }
  if (kind === "chat" && models.length === 0) {
    throw new CopilotProfileError(`${path}: '${key}' must list at least one model`);
  }
  const seen = new Map<string, number>();
  models.forEach((model, index) => {
    const where = `${path}: ${key}[${index}]`;
    if (!isRecord(model)) {
      throw new CopilotProfileError(`${where} must be a mapping`);
    }
    validateProfileModel(where, model);
    const identity = JSON.stringify([model.provider, model.name]);
    const first = seen.get(identity);
    if (first !== undefined) {
      throw new CopilotProfileError(`${where} repeats the provider and name of ${key}[${first}]`);
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
