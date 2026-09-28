import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    tsconfigPaths: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    // Node 25+ enables Web Storage by default, which shadows jsdom's localStorage.
    execArgv: ["--no-experimental-webstorage"],
  },
});
