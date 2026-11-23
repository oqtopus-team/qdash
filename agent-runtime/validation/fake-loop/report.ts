/**
 * The validation report: one JSON record and a short Markdown summary.
 *
 * Before anything is written (the report and every session artifact), every
 * string is passed through `redact`, which replaces the values of the run's
 * secrets (`effectiveSecrets`) and bearer or key-like strings.
 */

import type { Check } from "./evaluate.ts";
import type { PreflightCheck } from "./qdash-api.ts";

export const REPORT_SCHEMA = "qdash.agent-fake-loop-validation.v1";

export type RunStatus = "passed" | "failed" | "blocked" | "not_run";
export type ScenarioStatus = "passed" | "failed" | "blocked" | "not_run";

export interface ScenarioReport {
  id: string;
  title: string;
  status: ScenarioStatus;
  reason?: string;
  started_at?: string;
  prompts: string[];
  session_ids: string[];
  execution_ids: string[];
  intervention_ids: string[];
  commit_ids: string[];
  /** Calibration sessions the scenario created, in a purpose-level scenario. */
  calibration_session_ids?: string[];
  fault_id?: string;
  transcript?: unknown;
  /** What the model said; a reported interpretation, not evidence. */
  reported_answer?: string;
  checks: Check[];
  artifacts: Record<string, string>;
}

export interface ValidationReport {
  schema: typeof REPORT_SCHEMA;
  run_id: string;
  started_at: string;
  finished_at: string;
  status: RunStatus;
  reason?: string;
  versions: Record<string, string | null>;
  model: { id: string; source: string; profile: string | null } | null;
  target: { qdash: string; project_id: string; chip_id: string; qid: string };
  limits: Record<string, number>;
  preflight: PreflightCheck[];
  setup: { ran: boolean; chip_created: boolean; executions: Array<{ task: string; execution_id: string; status: string }> };
  scenarios: ScenarioReport[];
  artifacts: Record<string, string>;
  /** What this run does not establish, whatever its status. */
  not_validated: string[];
}

export const NOT_VALIDATED = [
  "Real hardware: every measurement ran on the fake backend's simulator.",
  "Scientific accuracy: the simulator's values are not physical measurements, and no check judges whether a fitted value is correct.",
  "External Slack delivery: the report records the intervention's notification status only.",
  "The QDash web Agent host: this harness drives the pi CLI host. The web host runs the same pi-qdash tools, so a pipeline it starts reports the same client-reported origin, but its chat, approval cards, and the web Execution pages are not exercised.",
  "Verified pipeline provenance: the origin a pipeline reports is client reported; QDash stores and shows it as reported and this run only checks that it is recorded and labeled so.",
];

const SECRET_NAME = /(TOKEN|SECRET|PASSWORD|API_KEY|_KEY$|CLIENT_ID|ACCESS)/i;
const PATTERNS: RegExp[] = [/Bearer\s+[A-Za-z0-9._~+/=-]{8,}/g, /\bsk-[A-Za-z0-9_-]{12,}/g, /\b(?:eyJ[A-Za-z0-9_-]{8,}\.){2}[A-Za-z0-9_-]{8,}/g];

/** The values of secret-looking variables in `env`, longest first. */
export function secretValues(env: NodeJS.ProcessEnv): string[] {
  return Object.entries(env)
    .filter(([name, value]) => SECRET_NAME.test(name) && typeof value === "string" && value.length >= 6)
    .map(([, value]) => value as string)
    .sort((a, b) => b.length - a.length);
}

/**
 * Every secret value of the run, longest first: secret-looking variables of the shell, of the
 * environment pi gets, and every value the launcher loaded into it from the env file (model
 * endpoints, keys, and the Access token), whatever its name.
 */
export function effectiveSecrets(env: NodeJS.ProcessEnv, plan?: { env: NodeJS.ProcessEnv; loaded: readonly string[] }): string[] {
  const values = new Set(secretValues(env));
  if (plan) {
    for (const value of secretValues(plan.env)) values.add(value);
    for (const name of plan.loaded) {
      const value = plan.env[name];
      if (typeof value === "string" && value.length >= 6) values.add(value);
    }
  }
  return [...values].sort((a, b) => b.length - a.length);
}

export function redact<T>(value: T, secrets: readonly string[]): T {
  if (typeof value === "string") {
    let text: string = value;
    for (const secret of secrets) text = text.split(secret).join("[redacted]");
    for (const pattern of PATTERNS) text = text.replace(pattern, "[redacted]");
    return text as T;
  }
  if (Array.isArray(value)) return value.map((item) => redact(item, secrets)) as T;
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, redact(item, secrets)])) as T;
  }
  return value;
}

export function renderMarkdown(report: ValidationReport): string {
  const lines = [
    `# Agent fake-loop validation ${report.run_id}`,
    "",
    `Status: **${report.status}**${report.reason ? ` (${report.reason})` : ""}`,
    "",
    `- QDash: ${report.target.qdash}, project ${report.target.project_id}, chip ${report.target.chip_id}, qubit ${report.target.qid}`,
    `- Model: ${report.model ? `${report.model.id} (${report.model.source}${report.model.profile ? `, profile ${report.model.profile}` : ""})` : "not started"}`,
    `- Versions: ${Object.entries(report.versions).map(([key, value]) => `${key} ${value ?? "unknown"}`).join(", ")}`,
    "",
    "## Preflight",
    "",
    ...report.preflight.map((check) => `- ${check.passed ? "pass" : "FAIL"} \`${check.id}\`: ${check.detail}`),
    "",
    "## Scenarios",
  ];
  for (const scenario of report.scenarios) {
    lines.push("", `### ${scenario.id}: ${scenario.status}`, "", scenario.title);
    if (scenario.reason) lines.push("", `Reason: ${scenario.reason}`);
    if (scenario.session_ids.length) lines.push("", `Sessions: ${scenario.session_ids.join(", ")}`);
    if (scenario.execution_ids.length) lines.push(`Executions: ${scenario.execution_ids.join(", ")}`);
    if (scenario.checks.length) {
      lines.push("", "| Check | Basis | Gating | Expected | Actual | Result |", "| --- | --- | --- | --- | --- | --- |");
      for (const check of scenario.checks) {
        const cell = (text: string) => text.replace(/\|/g, "\\|").replace(/\n/g, " ");
        lines.push(`| ${cell(check.id)} | ${check.basis} | ${check.gating ? "yes" : "no"} | ${cell(check.expected)} | ${cell(check.actual)} | ${check.passed ? "pass" : "FAIL"} |`);
      }
    }
  }
  lines.push("", "## Not validated by this run", "", ...report.not_validated.map((item) => `- ${item}`), "");
  return lines.join("\n");
}
