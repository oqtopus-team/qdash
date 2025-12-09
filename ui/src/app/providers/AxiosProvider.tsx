"use client";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

const PROJECT_STORAGE_KEY = "qdash_current_project_id";

export default function AxiosProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  // Configure base URL - use /api proxy route (handled by Next.js rewrites)
  // Falls back to direct API URL for backward compatibility
  AXIOS_INSTANCE.defaults.baseURL = process.env.NEXT_PUBLIC_API_URL || "/api";

  // Add request interceptor to handle auth and project context
  AXIOS_INSTANCE.interceptors.request.use((config) => {
    // Get token from cookies (which contains the username)
    const token = document.cookie
      .split("; ")
      .find((row) => row.startsWith("token="))
      ?.split("=")[1];

    if (token) {
      try {
        const decodedUsername = decodeURIComponent(token);
        // Set both Authorization and X-Username headers
        config.headers.Authorization = `Bearer ${decodedUsername}`;
        config.headers["X-Username"] = decodedUsername;
      } catch (error) {
        console.error("Failed to decode token:", error);
      }
    }

    // Get current project from localStorage
    const projectId = localStorage.getItem(PROJECT_STORAGE_KEY);
    if (projectId) {
      config.headers["X-Project-Id"] = projectId;
    }

    return config;
  });

  return children;
}
