/** @type {import('next').NextConfig} */
const allowedDevOrigins = (process.env.NEXT_ALLOWED_DEV_ORIGINS || "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

// The browser reaches the API at /api and Prefect at /prefect through Caddy
// (config/caddy/Caddyfile), in production and under `task dev-local` alike, so
// Next.js serves only the UI and needs no rewrites.
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
      // The task duration breakdown page was folded into the Execution page's activity chart.
      { source: "/execution/durations", destination: "/execution", permanent: true },
      { source: "/task-knowledge/:taskName", destination: "/knowledge/:taskName", permanent: true },
      // The knowledge file editor was removed: Knowledge is read-only.
      { source: "/knowledge/files", destination: "/knowledge", permanent: false },
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
    ],
  },
  pageExtensions: ["tsx", "ts"],
  useFileSystemPublicRoutes: true,
};

module.exports = nextConfig;
