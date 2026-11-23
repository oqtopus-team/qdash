import { join } from "node:path";

import { getAgentDir } from "@earendil-works/pi-coding-agent";

/**
 * Where pi-qdash keeps the chip and profile selection that outlives a session.
 *
 * It sits in pi's agent directory, so `PI_CODING_AGENT_DIR` moves it with the
 * rest of pi's state; unset, that is ~/.pi/agent.
 */
export function qdashContextPath(agentDir: string = getAgentDir()): string {
  return join(agentDir, "qdash-context.json");
}
