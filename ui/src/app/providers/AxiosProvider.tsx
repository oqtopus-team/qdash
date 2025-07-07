"use client";

import { AXIOS_INSTANCE } from "@/lib/custom-instance";

export default function AxiosProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  // Configure base URL
  AXIOS_INSTANCE.defaults.baseURL = process.env.NEXT_PUBLIC_API_URL;

  // Add request interceptor to handle auth
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

    return config;
  });

  return children;
}
