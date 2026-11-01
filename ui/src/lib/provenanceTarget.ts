/** A published parameter value: the parameter name and the qubit or coupling it belongs to. */
export interface ProvenanceTarget {
  parameterName: string;
  qid: string;
}

/**
 * Qubit or coupling a parameter belongs to, given the task's target and the parameter's role.
 * A coupling task writes some of its outputs to one of the two qubits (`control` or `target`).
 */
export function resolveParameterQid(taskQid: string, qidRole?: string): string {
  if (!qidRole || qidRole === "self" || qidRole === "coupling") return taskQid;
  const match = taskQid.match(/^(\d+)-(\d+)$/);
  if (!match) return taskQid;
  const [, control, target] = match;
  if (qidRole === "control") return control;
  if (qidRole === "target") return target;
  return taskQid;
}

function targetOf(taskQid: string, key: string, value: unknown): ProvenanceTarget {
  const record = (value && typeof value === "object" ? value : {}) as Record<string, unknown>;
  const parameterName =
    typeof record.parameter_name === "string" && record.parameter_name
      ? record.parameter_name
      : key;
  const qidRole = typeof record.qid_role === "string" ? record.qid_role : undefined;
  return { parameterName, qid: resolveParameterQid(taskQid, qidRole) };
}

/** Every output a task published, one entry per distinct parameter and target. */
export function publishedParameters(
  taskQid: string,
  outputParameters: Record<string, unknown> | null | undefined,
): ProvenanceTarget[] {
  const seen = new Set<string>();
  const targets: ProvenanceTarget[] = [];
  for (const [key, value] of Object.entries(outputParameters ?? {})) {
    const target = targetOf(taskQid, key, value);
    const id = `${target.parameterName}:${target.qid}`;
    if (seen.has(id)) continue;
    seen.add(id);
    targets.push(target);
  }
  return targets;
}

/**
 * The parameter a task's lineage opens on: its first output, or its first input when it produced
 * nothing. Null when the task has neither.
 */
export function firstPublishedParameter(
  taskQid: string,
  outputParameters: Record<string, unknown> | null | undefined,
  inputParameters: Record<string, unknown> | null | undefined,
): ProvenanceTarget | null {
  const [entry] = [
    ...Object.entries(outputParameters ?? {}),
    ...Object.entries(inputParameters ?? {}),
  ];
  return entry ? targetOf(taskQid, entry[0], entry[1]) : null;
}

/** Entity ID of the version a task wrote; mirrors `ParameterVersionDocument.generate_entity_id`. */
export function entityIdFor(target: ProvenanceTarget, executionId: string, taskId: string): string {
  return `${target.parameterName}:${target.qid}:${executionId}:${taskId}`;
}
