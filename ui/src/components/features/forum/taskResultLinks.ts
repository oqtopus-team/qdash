const TASK_RESULT_LINK_RE = /(?:https?:\/\/[^\s/]+)?\/task-results\/([^\s/?#)\]}>,"']+)/g;

const MAX_TASK_RESULT_PREVIEWS = 3;

function collectStrings(value: unknown, strings: string[]): void {
  if (typeof value === "string") {
    strings.push(value);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => collectStrings(item, strings));
    return;
  }
  if (value && typeof value === "object") {
    Object.values(value).forEach((item) => collectStrings(item, strings));
  }
}

/** Find unique task-result IDs linked from legacy Markdown or BlockNote content. */
export function extractLinkedTaskResultIds(
  content: string,
  blocks: Record<string, unknown>[],
): string[] {
  const strings = [content];
  collectStrings(blocks, strings);

  const ids = new Set<string>();
  for (const value of strings) {
    for (const match of value.matchAll(TASK_RESULT_LINK_RE)) {
      try {
        ids.add(decodeURIComponent(match[1]));
      } catch {
        ids.add(match[1]);
      }
      if (ids.size === MAX_TASK_RESULT_PREVIEWS) return [...ids];
    }
  }
  return [...ids];
}
