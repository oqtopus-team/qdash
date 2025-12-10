/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    // Proxy /api/* to backend API server
    // This allows UI-only deployment without exposing API port
    const apiUrl = process.env.INTERNAL_API_URL || "http://localhost:5715";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
  transpilePackages: ["react-plotly.js", "plotly.js-basic-dist"],
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
