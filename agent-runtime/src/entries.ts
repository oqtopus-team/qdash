/**
 * Rebuild Pi session entries from the message list stored in MongoDB.
 *
 * QDash owns the conversation, so every request starts from an in-memory
 * SessionManager seeded with the previous turns.
 * See .agent/sessions/2026-09-18-copilot-pi-agent-runtime/adr/0002-*.md
 */

let counter = 0;

function nextId(): string {
  counter = (counter + 1) % 0xffffffff;
  return counter.toString(16).padStart(8, "0");
}

/** Build a session header plus one message entry per stored message. */
export function buildEntries(cwd: string, sessionId: string, messages: unknown[]): unknown[] {
  const timestamp = new Date().toISOString();
  const entries: unknown[] = [
    { type: "session", version: 3, id: sessionId, timestamp, cwd },
  ];

  let parentId: string | null = null;
  for (const message of messages) {
    const id = nextId();
    entries.push({ type: "message", id, parentId, timestamp, message });
    parentId = id;
  }
  return entries;
}
