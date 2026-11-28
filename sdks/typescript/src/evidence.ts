/**
 * One task result joined with the context needed to read it, from existing
 * read endpoints only: `qdash.taskResults.evidence(taskId)`.
 *
 * Each context part is a `TaskResultContext`: its value when it was read, or
 * the reason it is absent. A failed or missing part is never filled from other
 * data, and a cooldown is never inferred.
 */
import { isRecord, read as readGet, type Context } from "./_http.js";
import { QDashApiError, QDashValidationError } from "./errors.js";
import type {
  CooldownResponse,
  CouplingResponse,
  ExecutionResponseDetail,
  QubitResponse,
  Task,
  TaskResultResponse,
} from "./types.js";

/**
 * A context part of the evidence.
 *
 * - `ok`: read; `value` holds it.
 * - `failed`: its read failed; `error` says why and `statusCode` is the HTTP
 *   status when QDash answered.
 * - `not_applicable`: the result has nothing to read it from (no execution ID,
 *   no qubit or coupling target, no chip).
 * - `not_associated`: QDash records no association to read it by.
 */
export type TaskResultContext<T> =
  | { status: "ok"; value: T }
  | { status: "failed"; error: string; statusCode?: number }
  | { status: "not_applicable"; reason: string }
  | { status: "not_associated"; reason: string };

export interface TaskResultEvidenceOptions {
  /**
   * A cooldown to check against the result. QDash's task result response does
   * not say which cooldown it was recorded in, so without this option the
   * cooldown part is `not_associated`.
   */
  cooldownId?: string;
}

export interface ExecutionContext {
  execution: ExecutionResponseDetail;
  /** This result's entry in the execution's tasks, or null when the execution does not list it. */
  task: Task | null;
  /** Whether the execution's chip is the result's; null when either is empty. */
  chipMatches: boolean | null;
}

/** The stored value of one parameter the result outputs. */
export interface StoredOutput {
  /** The target's current stored entry for the parameter. */
  stored: unknown;
  /** Whether that entry names this result as its task; null when it names no task. */
  fromThisResult: boolean | null;
}

export interface TargetContext {
  kind: "qubit" | "coupling";
  /** The result's qid: a qubit (`"6"`) or coupling (`"6-7"`) ID. */
  id: string;
  /** Where `kind` came from: the execution's task entry, else the qid format. */
  kindSource: "execution_task_type" | "qid_format";
  /** The target's current state as QDash stores it. */
  state: QubitResponse | CouplingResponse;
  /** Current stored values of the parameters the result outputs, by name; they may come from a later result. */
  outputs: Record<string, StoredOutput>;
  /** Output parameter names the target stores no value for. */
  outputsNotStored: string[];
}

export interface CooldownContext {
  cooldown: CooldownResponse;
  /** The cooldown was named by the caller; QDash does not report that the result was recorded in it. */
  association: "named";
  /** Whether the named cooldown is consistent with the result; null when the data to check is missing. */
  checks: {
    chipListed: boolean | null;
    resultStartWithin: boolean | null;
  };
}

export interface TaskResultEvidence {
  taskId: string;
  /** The result as `GET /tasks/{task_id}/result` returns it; its status is QDash's own. */
  result: TaskResultResponse;
  execution: TaskResultContext<ExecutionContext>;
  target: TaskResultContext<TargetContext>;
  cooldown: TaskResultContext<CooldownContext>;
}

/** Why the cooldown part is `not_associated` when no cooldown is named. */
export const COOLDOWN_NOT_ASSOCIATED =
  "QDash's task result response does not include the cooldown the result was recorded in; no cooldown is inferred from times or from the chip's current cooldown. Name one with cooldownId to check it against the result.";

const EVIDENCE_OPTIONS = new Set(["cooldownId"]);

function text(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

function checkEvidenceArguments(taskId: unknown, options: unknown): void {
  const problems: string[] = [];
  if (typeof taskId !== "string" || taskId.trim() === "") problems.push("taskId is required");
  const raw = (options ?? {}) as Record<string, unknown>;
  if (!isRecord(raw)) problems.push("options must be an object");
  else {
    if (raw.cooldownId !== undefined && (typeof raw.cooldownId !== "string" || raw.cooldownId.trim() === "")) {
      problems.push("cooldownId must be a non-empty string");
    }
    const unknown = Object.keys(raw).filter((key) => raw[key] !== undefined && !EVIDENCE_OPTIONS.has(key));
    if (unknown.length > 0) {
      problems.push(`${unknown.join(", ")} ${unknown.length === 1 ? "is not an option" : "are not options"} of evidence`);
    }
  }
  if (problems.length > 0) throw new QDashValidationError(`${problems.join("; ")}.`, { body: { problems } });
}

/** A failed read as a context part, keeping the error kind and HTTP status. */
function failed(error: unknown): { status: "failed"; error: string; statusCode?: number } {
  if (error instanceof Error) {
    const statusCode = error instanceof QDashApiError ? error.statusCode : undefined;
    return {
      status: "failed",
      error: `${error.name}: ${error.message}`,
      ...(typeof statusCode === "number" ? { statusCode } : {}),
    };
  }
  return { status: "failed", error: String(error) };
}

async function read<T>(load: () => Promise<T>): Promise<TaskResultContext<T>> {
  try {
    return { status: "ok", value: await load() };
  } catch (error) {
    return failed(error);
  }
}

/** Output parameter names of the result: its listed names and its output keys. */
export function outputParameterNames(result: TaskResultResponse): string[] {
  const listed = Array.isArray(result.output_parameter_names)
    ? result.output_parameter_names.filter((name): name is string => typeof name === "string")
    : [];
  const outputs = isRecord(result.output_parameters) ? Object.keys(result.output_parameters) : [];
  return [...new Set([...listed, ...outputs])];
}

/** The result's target kind: the execution task's `task_type` when it says, else a qid with `-` is a coupling. */
export function targetKind(qid: string, task: Task | null): Pick<TargetContext, "kind" | "kindSource"> {
  const type = task?.task_type;
  if (type === "qubit" || type === "coupling") return { kind: type, kindSource: "execution_task_type" };
  return { kind: qid.includes("-") ? "coupling" : "qubit", kindSource: "qid_format" };
}

function executionContext(execution: ExecutionResponseDetail, result: TaskResultResponse): ExecutionContext {
  if (!isRecord(execution)) {
    throw new QDashApiError(`Unexpected GET /executions/${result.execution_id} response: not an object`, { body: execution });
  }
  const tasks = Array.isArray(execution.task) ? execution.task : [];
  const task = tasks.find((entry) => isRecord(entry) && entry.task_id === result.task_id) ?? null;
  const executionChip = text(execution.chip_id);
  const resultChip = text(result.chip_id);
  return { execution, task, chipMatches: executionChip && resultChip ? executionChip === resultChip : null };
}

function targetContext(
  state: QubitResponse | CouplingResponse,
  kind: Pick<TargetContext, "kind" | "kindSource">,
  result: TaskResultResponse,
): TargetContext {
  if (!isRecord(state)) throw new QDashApiError(`Unexpected ${kind.kind} response for ${result.qid}: not an object`, { body: state });
  const data = isRecord(state.data) ? state.data : {};
  const outputs: Record<string, StoredOutput> = {};
  const outputsNotStored: string[] = [];
  for (const name of outputParameterNames(result)) {
    if (!(name in data)) {
      outputsNotStored.push(name);
      continue;
    }
    const stored = data[name];
    const storedTask = isRecord(stored) ? text(stored.task_id) : undefined;
    outputs[name] = { stored, fromThisResult: storedTask ? storedTask === result.task_id : null };
  }
  return { ...kind, id: result.qid, state, outputs, outputsNotStored };
}

function cooldownContext(cooldown: CooldownResponse, result: TaskResultResponse): CooldownContext {
  if (!isRecord(cooldown)) throw new QDashApiError("Unexpected cooldown response: not an object", { body: cooldown });
  const chip = text(result.chip_id);
  const chips = Array.isArray(cooldown.chip_ids) ? cooldown.chip_ids : null;
  const at = Date.parse(text(result.start_at) ?? "");
  const started = Date.parse(text(cooldown.started_at) ?? "");
  const endedText = text(cooldown.ended_at);
  const ended = endedText ? Date.parse(endedText) : Number.POSITIVE_INFINITY;
  const timed = Number.isFinite(at) && Number.isFinite(started) && !Number.isNaN(ended);
  return {
    cooldown,
    association: "named",
    checks: {
      chipListed: chip && chips ? chips.includes(chip) : null,
      resultStartWithin: timed ? at >= started && at <= ended : null,
    },
  };
}

/**
 * Read one task result and join its execution, the current state of its
 * qubit or coupling, and a named cooldown. See `TaskResults.evidence`.
 */
export async function readTaskResultEvidence(
  context: Context,
  taskId: string,
  options: TaskResultEvidenceOptions = {},
): Promise<TaskResultEvidence> {
  checkEvidenceArguments(taskId, options);
  const id = taskId.trim();
  const { api, reads } = context;
  const body: unknown = await readGet(reads, (requestOptions) => api.task.getTaskResult({ task_id: id }, requestOptions));
  if (!isRecord(body)) throw new QDashApiError(`Unexpected GET /tasks/${id}/result response: not an object`, { body: body });
  if (body.task_id !== id) {
    throw new QDashApiError(`The result read for ${id} has task_id ${JSON.stringify(body.task_id)}`, { body: body });
  }
  const result = body as unknown as TaskResultResponse;

  const executionId = text(result.execution_id);
  const execution: TaskResultContext<ExecutionContext> = executionId
    ? await read(async () => executionContext(await readGet(reads, (requestOptions) => api.execution.getExecution({ execution_id: executionId }, requestOptions)), result))
    : { status: "not_applicable", reason: "The task result names no execution." };

  const qid = text(result.qid);
  const chipId = text(result.chip_id);
  let target: TaskResultContext<TargetContext>;
  if (!qid) target = { status: "not_applicable", reason: "The task result has no qubit or coupling target (empty qid)." };
  else if (!chipId) target = { status: "not_applicable", reason: "The task result names no chip, so its target cannot be read." };
  else {
    const kind = targetKind(qid, execution.status === "ok" ? execution.value.task : null);
    target = await read(async () =>
      targetContext(
        kind.kind === "coupling"
          ? await readGet(reads, (requestOptions) =>
              api.chip.getChipCoupling({ chip_id: chipId, coupling_id: qid }, requestOptions),
            )
          : await readGet(reads, (requestOptions) => api.chip.getChipQubit({ chip_id: chipId, qid }, requestOptions)),
        kind,
        result,
      ),
    );
  }

  const cooldownId = options.cooldownId?.trim();
  const cooldown: TaskResultContext<CooldownContext> = cooldownId
    ? await read(async () => cooldownContext(await readGet(reads, (requestOptions) => api.cooldown.getCooldown({ cooldown_id: cooldownId }, requestOptions)), result))
    : { status: "not_associated", reason: COOLDOWN_NOT_ASSOCIATED };

  return { taskId: id, result, execution, target, cooldown };
}
