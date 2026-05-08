import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: '/divisions/:path*.json',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=300, s-maxage=86400, stale-while-revalidate=86400',
          },
          { key: 'Content-Type', value: 'application/json; charset=utf-8' },
        ],
      },
      {
        source: '/data.json',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=300, s-maxage=86400',
          },
        ],
      },
    ];
  },
};

export default nextConfig;
