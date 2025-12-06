/** @type {import('next').NextConfig} */
const nextConfig = {
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
  transpilePackages: ["react-plotly.js", "plotly.js"],
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
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      "plotly.js": "plotly.js/dist/plotly",
    };
    return config;
  },
};

module.exports = nextConfig;
