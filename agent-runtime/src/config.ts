import { readFileSync } from "node:fs";

import { parse } from "yaml";

/** Language settings read from QDash's shared copilot config. */
export interface LanguageConfig {
  responseLanguage: string;
  thinkingLanguage: string;
}

const FALLBACK: LanguageConfig = { responseLanguage: "en", thinkingLanguage: "en" };

/**
 * Read `response_language` / `thinking_language` from config/copilot/config.yaml.
 *
 * Only the language keys are used here. Model selection is wired through
 * models.json instead, see adr/0004.
 */
export function loadLanguageConfig(path: string): LanguageConfig {
  try {
    const raw = parse(readFileSync(path, "utf8")) as Record<string, unknown> | null;
    return {
      responseLanguage: asString(raw?.response_language) ?? FALLBACK.responseLanguage,
      thinkingLanguage: asString(raw?.thinking_language) ?? FALLBACK.thinkingLanguage,
    };
  } catch (error) {
    console.warn(`[agent-runtime] could not read ${path}, using defaults:`, error);
    return FALLBACK;
  }
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}
