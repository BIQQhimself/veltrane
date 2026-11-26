import type { NextConfig } from "next";

// Render Static Sites serve pre-built files, so the deployment build sets
// VELTRANE_STATIC_EXPORT=1. Local development and CI keep the normal server build.
const staticExport = process.env.VELTRANE_STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  ...(staticExport
    ? { output: "export" as const, trailingSlash: true, images: { unoptimized: true } }
    : {}),
  // Single-origin deployments (one public host, API behind the same host) set
  // VELTRANE_API_PROXY=http://127.0.0.1:8000 so the browser never crosses origins.
  async rewrites() {
    if (staticExport) return [];
    const target = process.env.VELTRANE_API_PROXY;
    return target ? [{ source: "/api/:path*", destination: `${target}/api/:path*` }] : [];
  },
  // A static host applies response headers from the host config instead (see render.yaml).
  async headers() {
    if (staticExport) return [];
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
