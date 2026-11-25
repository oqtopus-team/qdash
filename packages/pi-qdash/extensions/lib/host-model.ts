/**
 * The model identity a host reports with QDash agent records.
 *
 * pi CLI passes the conversation's model in the extension context
 * (`ctx.model`, a pi-ai `Model` with `provider` and `id`). The QDash web Agent
 * also sets `HOST_MODEL_KEY` to the model reference its durable harness runs
 * the conversation with, which holds even when the model is not in the
 * runtime's catalog, and for an approved write, the model that made the call.
 * pi-qdash sends that provider and model ID with each session, action,
 * decision, and intervention it records, so QDash can attribute every step to
 * the model that took it, including after a model switch or a resume in
 * another host. Tool arguments never supply it: a model cannot claim another
 * identity, and no tool schema offers one.
 *
 * Only identifiers leave the host: no endpoint URL, API key, prompt, or
 * reasoning. An identity that is missing or does not look like an identifier
 * is left out, and QDash shows it as not reported rather than guessing.
 */
import type { AgentModelIdentity } from "./qdash-connection.js";

/**
 * Extension-context key naming the host when it is not pi itself. The QDash
 * web Agent sets `"qdash-web-agent"`; only host code builds the context.
 */
export const HOST_NAME_KEY = "qdashHostName";

/**
 * Extension-context key a host sets to the provider and model ID it runs the
 * conversation with, when that is more exact than `ctx.model`. Preferred over
 * `ctx.model`; only host code builds the context.
 */
export const HOST_MODEL_KEY = "qdashHostModel";

/** The host label when none is set: the extension runs inside pi. */
export const DEFAULT_HOST_NAME = "pi";

interface ModelReference {
  provider?: unknown;
  id?: unknown;
}

export interface HostModelContext {
  model?: ModelReference | undefined;
  [HOST_MODEL_KEY]?: ModelReference | undefined;
  [HOST_NAME_KEY]?: unknown;
}

// Mirrors QDash's AgentModelIdentity validation, so a reported identity never
// makes QDash refuse the write it accompanies.
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$/;
const HOST = /^[a-z0-9][a-z0-9._-]*$/;

function identifier(value: unknown, maxLength: number): string | undefined {
  if (typeof value !== "string" || value.length > maxLength) return undefined;
  if (!IDENTIFIER.test(value) || value.includes("://")) return undefined;
  return value;
}

/** The provider and model of the host's current model, or undefined when the host has none. */
export function hostModelIdentity(ctx: HostModelContext | undefined): AgentModelIdentity | undefined {
  const model = ctx?.[HOST_MODEL_KEY] ?? ctx?.model;
  const provider = identifier(model?.provider, 100);
  const modelId = identifier(model?.id, 200);
  if (!provider || !modelId) return undefined;
  const named = ctx?.[HOST_NAME_KEY];
  const host = typeof named === "string" && named.length <= 64 && HOST.test(named) ? named : DEFAULT_HOST_NAME;
  return { provider, model_id: modelId, host };
}
