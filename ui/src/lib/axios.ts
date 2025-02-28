import axios from "axios";

// Configure global axios defaults
axios.defaults.baseURL = "http://localhost:5715";

// Add request interceptor to handle auth
axios.interceptors.request.use((config) => {
  // Get token from cookie
  const token = document.cookie
    .split("; ")
    .find((row) => row.startsWith("token="))
    ?.split("=")[1];

  if (token) {
    try {
      const decodedToken = decodeURIComponent(token);
      config.headers.Authorization = `Bearer ${decodedToken}`;
    } catch (error) {
      console.error("Failed to decode token:", error);
    }
  }

  return config;
});

export default axios;
