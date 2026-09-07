import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_INTERNAL_URL || (process.env.NODE_ENV === "production" ? "http://backend:8000" : "http://127.0.0.1:8001");

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
