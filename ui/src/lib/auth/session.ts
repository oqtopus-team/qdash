const ACCESS_TOKEN_COOKIE = "access_token";
const PROJECT_STORAGE_KEY = "qdash_current_project_id";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") {
    return null;
  }

  const cookie = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`))
    ?.split("=")[1];

  if (!cookie) {
    return null;
  }

  try {
    return decodeURIComponent(cookie);
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  return readCookie(ACCESS_TOKEN_COOKIE);
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

  const accessToken = getAccessToken();
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  const projectId = getProjectId();
  if (projectId) {
    headers["X-Project-Id"] = projectId;
  }

  return headers;
}
