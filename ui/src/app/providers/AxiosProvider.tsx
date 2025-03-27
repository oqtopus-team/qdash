"use client";

import { AXIOS_INSTANCE } from "@/lib/custom-instance";

export default function AxiosProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  // Configure base URL
  AXIOS_INSTANCE.defaults.baseURL = "http://localhost:5715";

  // Add request interceptor to handle auth
  AXIOS_INSTANCE.interceptors.request.use((config) => {
    // Get token and username from cookies
    const token = document.cookie
      .split("; ")
      .find((row) => row.startsWith("token="))
      ?.split("=")[1];

    const username = document.cookie
      .split("; ")
      .find((row) => row.startsWith("username="))
      ?.split("=")[1];

    if (token) {
      try {
        const decodedToken = decodeURIComponent(token);
        config.headers.Authorization = `Bearer ${decodedToken}`;
      } catch (error) {
        console.error("Failed to decode token:", error);
      }
    }

    if (username) {
      try {
        const decodedUsername = decodeURIComponent(username);
        config.headers["X-Username"] = decodedUsername;
      } catch (error) {
        console.error("Failed to decode username:", error);
      }
    }

    return config;
  });

  return children;
}
