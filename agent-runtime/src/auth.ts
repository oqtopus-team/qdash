/**
 * Obtain the QDash API token the pi-qdash extension authenticates with.
 *
 * QDash creates its administrator from QDASH_ADMIN_USERNAME/PASSWORD on API
 * startup, so the runtime can log in and derive a token instead of requiring an
 * operator to provision a service account and paste QDASH_API_TOKEN by hand.
 *
 * An explicit QDASH_API_TOKEN still wins, which is how a deployment can hand the
 * runtime a narrower account.
 */
export async function resolveQDashApiToken(): Promise<void> {
  if (process.env.QDASH_API_TOKEN) {
    console.log("[agent-runtime] using QDASH_API_TOKEN from the environment");
    return;
  }

  const baseUrl = process.env.QDASH_BASE_URL;
  const username = process.env.QDASH_ADMIN_USERNAME;
  const password = process.env.QDASH_ADMIN_PASSWORD;
  if (!baseUrl || !username || !password) {
    throw new Error(
      "Cannot authenticate to QDash: set QDASH_API_TOKEN, or QDASH_BASE_URL with QDASH_ADMIN_USERNAME and QDASH_ADMIN_PASSWORD.",
    );
  }

  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),
  });
  if (!response.ok) {
    throw new Error(`QDash login failed for ${username}: HTTP ${response.status}`);
  }

  const { access_token: accessToken, default_project_id: defaultProjectId } =
    (await response.json()) as { access_token?: string; default_project_id?: string };
  if (!accessToken) {
    throw new Error("QDash login returned no access_token");
  }

  process.env.QDASH_API_TOKEN = accessToken;
  if (!process.env.QDASH_PROJECT_ID && defaultProjectId) {
    process.env.QDASH_PROJECT_ID = defaultProjectId;
  }
  console.log(
    `[agent-runtime] authenticated to QDash as ${username} (project ${process.env.QDASH_PROJECT_ID ?? "unset"})`,
  );
}
