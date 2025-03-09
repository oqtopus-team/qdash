/** @type {import('next').NextConfig} */
const nextConfig = {
  rewrites: async () => {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:5716/api/:path*",
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
