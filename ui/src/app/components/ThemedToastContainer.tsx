"use client";

import { ToastContainer } from "react-toastify";

import "react-toastify/dist/ReactToastify.css";
import { useTheme } from "../providers/theme-provider";

export function ThemedToastContainer() {
  const { theme } = useTheme();

  return (
    <ToastContainer
      position="top-right"
      autoClose={5000}
      hideProgressBar={false}
      newestOnTop={false}
      closeOnClick
      rtl={false}
      pauseOnFocusLoss
      draggable
      pauseOnHover
      theme={theme === "light" ? "light" : "dark"}
    />
  );
}
