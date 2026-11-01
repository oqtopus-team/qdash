/** @type {import('next').NextConfig} */
const allowedDevOrigins = (process.env.NEXT_ALLOWED_DEV_ORIGINS || "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig = {
  output: "standalone",
  ...(allowedDevOrigins.length > 0 ? { allowedDevOrigins } : {}),
  async redirects() {
    // Pages renamed in 2026-10: the Files editor is Config, Task Knowledge is Knowledge.
    return [
      { source: "/files", destination: "/config", permanent: true },
      { source: "/task-knowledge", destination: "/knowledge", permanent: true },
      // Provenance is shown on task results, metric history and executions; the page is gone.
      { source: "/provenance", destination: "/analysis", permanent: true },
      { source: "/task-knowledge/:taskName", destination: "/knowledge/:taskName", permanent: true },
      // The knowledge file editor was removed: Knowledge is read-only.
      { source: "/knowledge/files", destination: "/knowledge", permanent: false },
    ];
  },
  async rewrites() {
    // Proxy /api/* to backend API server
    // This allows UI-only deployment without exposing API port
    const apiUrl = process.env.INTERNAL_API_URL || "http://127.0.0.1:5715";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
  transpilePackages: ["react-plotly.js", "plotly.js-dist-min"],
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "github.com",
        port: "",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "raw.githubusercontent.com",
        port: "",
        pathname: "/microsoft/fluentui-emoji/**",
      },
    ],
  },
  pageExtensions: ["tsx", "ts"],
  useFileSystemPublicRoutes: true,
};

module.exports = nextConfig;
