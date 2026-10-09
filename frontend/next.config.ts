import type { NextConfig } from "next";

const BACKEND_URL = "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/v1/:path*", destination: `${BACKEND_URL}/v1/:path*` }];
  },
};

export default nextConfig;
