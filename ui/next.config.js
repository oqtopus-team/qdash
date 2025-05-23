/** @type {import('next').NextConfig} */
const nextConfig = {
  rewrites: async () => {
    return [
      {
        source: "/api/:path*",
        destination: process.env.NEXT_PUBLIC_API_URL + "/api/:path*",
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
