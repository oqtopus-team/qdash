import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

/** Supplied by the authenticated API request, never by the model or durable state. */
export interface QDashAuth {
  accessToken: string;
  projectId?: string;
}

export interface QDashConnection {
  readonly auth: QDashAuth;
  readonly baseUrl: string;
  readonly toolArgs: { profile: string; configPath: string; useEnv: false };
  close(): Promise<void>;
}

export function requestQDashAuth(
  headers: Record<string, string | string[] | undefined>,
): QDashAuth {
  const accessToken = headers["x-qdash-token"];
  const projectId = headers["x-qdash-project-id"];
  if (typeof accessToken !== "string" || !accessToken.trim()) {
    throw new Error("QDash user token is required");
  }
  if (projectId !== undefined && (typeof projectId !== "string" || !projectId.trim())) {
    throw new Error("Invalid QDash project ID");
  }
  return { accessToken, ...(projectId ? { projectId } : {}) };
}

/**
 * The pinned pi-qdash accepts a config path, not an injected client. Give each
 * open harness its own private, temporary profile, removed when it closes.
 * Never read ambient tokens, passwords, projects, or local client profiles.
 */
export async function createQDashConnection(auth: QDashAuth): Promise<QDashConnection> {
  if (!auth.accessToken?.trim()) throw new Error("QDash user token is required");
  const baseUrl = process.env.QDASH_BASE_URL?.replace(/\/$/, "");
  if (!baseUrl) throw new Error("QDASH_BASE_URL is required");
  const directory = await mkdtemp(join(tmpdir(), "qdash-auth-"));
  const configPath = join(directory, "config.ini");
  const close = () => rm(directory, { recursive: true, force: true });
  try {
    // JSON quoting is understood by the client's INI parser and prevents values
    // from introducing extra keys or profiles.
    const values = {
      base_url: baseUrl,
      api_token: auth.accessToken,
      ...(auth.projectId ? { project_id: auth.projectId } : {}),
    };
    await writeFile(
      configPath,
      `[runtime]\n${Object.entries(values)
        .map(([key, value]) => `${key} = ${JSON.stringify(value)}`)
        .join("\n")}\n`,
      { mode: 0o600 },
    );
    return {
      auth: { ...auth },
      baseUrl,
      toolArgs: { profile: "runtime", configPath, useEnv: false },
      close,
    };
  } catch (error) {
    await close();
    throw error;
  }
}
