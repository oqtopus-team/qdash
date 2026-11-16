/**
 * A choice remembered in localStorage that every mounted surface reads live.
 *
 * Writes notify the surfaces of this tab at once, and the `storage` event
 * carries writes from other tabs, so Settings, the chat page, and the docked
 * chat never show different choices.
 */
export interface StoredChoice<T extends string> {
  read: () => T;
  write: (value: T) => void;
  subscribe: (listener: () => void) => () => void;
  /** The value before the browser storage is readable (server render, hydration). */
  initial: T;
}

export function createStoredChoice<T extends string>(
  storageKey: string,
  parse: (raw: string | null) => T,
): StoredChoice<T> {
  const listeners = new Set<() => void>();
  const initial = parse(null);
  let memoryChoice: T | undefined;

  const read = () => {
    if (typeof window === "undefined") return initial;
    if (memoryChoice !== undefined) return memoryChoice;
    try {
      return parse(localStorage.getItem(storageKey));
    } catch {
      return initial;
    }
  };

  const write = (value: T) => {
    if (typeof window === "undefined") return;
    memoryChoice = value;
    try {
      localStorage.setItem(storageKey, value);
      memoryChoice = undefined;
    } catch {
      // Remembering the choice is a convenience; the selection still applies.
    }
    listeners.forEach((listener) => listener());
  };

  const subscribe = (listener: () => void) => {
    listeners.add(listener);
    const onStorage = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null) {
        memoryChoice = undefined;
        listener();
      }
    };
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(listener);
      window.removeEventListener("storage", onStorage);
    };
  };

  return { read, write, subscribe, initial };
}
