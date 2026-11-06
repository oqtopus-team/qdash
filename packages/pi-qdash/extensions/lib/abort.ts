/**
 * Stop waiting when the host cancels the call.
 *
 * The client's polling helpers (`waitForExecution` and friends) run until the
 * execution finishes or their own timeout passes; they take no signal. A tool
 * that awaits one directly keeps a cancelled turn alive until then: the host
 * cannot end the turn, and the chat refuses the next message because the
 * conversation is still busy. This races the wait against the signal, so the
 * call returns as cancelled at once; the poll it leaves behind only reads.
 */
export class WaitCancelled extends Error {
  override readonly name = "AbortError";
  constructor(what: string) {
    super(`${what} was cancelled before it finished; the execution itself keeps running in QDash.`);
  }
}

export function withAbort<T>(promise: Promise<T>, signal: AbortSignal | undefined, what: string): Promise<T> {
  if (!signal) return promise;
  if (signal.aborted) return Promise.reject(new WaitCancelled(what));
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(new WaitCancelled(what));
    signal.addEventListener("abort", onAbort, { once: true });
    promise.then(resolve, reject).finally(() => signal.removeEventListener("abort", onAbort));
  });
}
