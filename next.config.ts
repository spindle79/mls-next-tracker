import type { NextConfig } from "next";

// The shards are rebuilt by refresh.sh while the dev server is running, so a
// browser cache there just serves last run's standings for five minutes. Cache
// hard in production (Vercel + CDN), never in dev.
const isDev = process.env.NODE_ENV === "development";
const shardCache = isDev
  ? "no-store, must-revalidate"
  : "public, max-age=300, s-maxage=86400, stale-while-revalidate=86400";
const dataCache = isDev ? "no-store, must-revalidate" : "public, max-age=300, s-maxage=86400";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/divisions/:path*.json",
        headers: [
          {
            key: "Cache-Control",
            value: shardCache,
          },
          { key: "Content-Type", value: "application/json; charset=utf-8" },
        ],
      },
      {
        source: "/data.json",
        headers: [
          {
            key: "Cache-Control",
            value: dataCache,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
