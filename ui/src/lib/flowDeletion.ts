import { getApiErrorMessage } from "@/lib/utils/apiError";

export interface FlowDeletionFailure {
  name: string;
  message: string;
}

export interface FlowDeletionResult {
  deleted: string[];
  failed: FlowDeletionFailure[];
}

/**
 * Delete flows one at a time through the single-flow endpoint and collect the
 * outcome of each. One request at a time keeps the load on the API and Prefect
 * bounded, and a failure never stops the remaining deletions.
 */
export async function deleteFlowsSequentially(
  names: readonly string[],
  deleteOne: (name: string) => Promise<unknown>,
  onProgress?: (done: number) => void,
): Promise<FlowDeletionResult> {
  const deleted: string[] = [];
  const failed: FlowDeletionFailure[] = [];
  for (const [index, name] of names.entries()) {
    try {
      await deleteOne(name);
      deleted.push(name);
    } catch (error) {
      failed.push({ name, message: getApiErrorMessage(error, "Unknown error") });
    }
    onProgress?.(index + 1);
  }
  return { deleted, failed };
}
