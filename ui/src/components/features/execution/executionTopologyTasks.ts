import type { Task } from "@/schemas";

export type TaskGroups = Record<string, Task[]>;

export interface GroupedExecutionTasks {
  oneQubit: TaskGroups;
  coupling: TaskGroups;
}

function normalizeQid(qid: string): string {
  const numericQid = Number.parseInt(qid.replace(/\D/g, ""), 10);
  return Number.isNaN(numericQid) ? qid : String(numericQid);
}

function compareQid(first: string, second: string): number {
  const firstNumber = Number(first);
  const secondNumber = Number(second);
  if (!Number.isNaN(firstNumber) && !Number.isNaN(secondNumber)) {
    return firstNumber - secondNumber;
  }
  return first.localeCompare(second);
}

/**
 * Groups execution tasks by the entity the topology grid draws: a qubit for
 * one-qubit tasks, a normalized `low-high` id for coupling tasks. Task order
 * inside a group is the execution order the API returns.
 */
export function groupTasksByEntity(tasks: Task[]): GroupedExecutionTasks {
  const oneQubit: TaskGroups = {};
  const coupling: TaskGroups = {};

  for (const task of tasks) {
    if (!task.qid) continue;
    if (task.qid.includes("-")) {
      const [first, second] = task.qid.split("-");
      if (!first || !second) continue;
      const couplingId = [normalizeQid(first), normalizeQid(second)].sort(compareQid).join("-");
      (coupling[couplingId] ??= []).push(task);
    } else {
      const qid = normalizeQid(task.qid);
      (oneQubit[qid] ??= []).push(task);
    }
  }

  return { oneQubit, coupling };
}

/**
 * Keeps only the entities that ran `taskName`, and only those task runs. This is
 * what the grid renders, so an empty `taskName` yields no entities.
 */
export function filterTaskGroupsByName(groups: TaskGroups, taskName: string): TaskGroups {
  if (!taskName) return {};
  const filtered: TaskGroups = {};
  for (const [entityId, entityTasks] of Object.entries(groups)) {
    const matched = entityTasks.filter((task) => task.name === taskName);
    if (matched.length > 0) filtered[entityId] = matched;
  }
  return filtered;
}

/**
 * Position of the task selected in the filter, used as the detail modal's
 * initial selection. Falls back to the first task when the name is not present.
 */
export function resolveInitialTaskIndex(tasks: Task[], taskName: string): number {
  if (!taskName) return 0;
  const index = tasks.findIndex((task) => task.name === taskName);
  return index >= 0 ? index : 0;
}
