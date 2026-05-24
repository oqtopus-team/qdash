const PROJECT_STORAGE_KEY = "qdash_current_project_id";

export function getAccessToken(): string | null {
  return null;
}

export function getProjectId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(PROJECT_STORAGE_KEY);
}

export function buildAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const projectId = getProjectId();
  if (projectId) {
    headers["X-Project-Id"] = projectId;
  }

  return headers;
}
