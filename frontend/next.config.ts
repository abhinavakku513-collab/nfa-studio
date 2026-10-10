import type { NextConfig } from "next";

// Where the /v1 rewrite forwards API calls when the browser does not call the API itself.
const BACKEND_URL = (
  process.env.BACKEND_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

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
