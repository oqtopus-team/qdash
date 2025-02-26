/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    appDir: true,
  },
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
  // Disable pages directory
  pageExtensions: ["tsx", "ts"],
  // Ensure app directory is used
  useFileSystemPublicRoutes: true,
};

export default nextConfig;
