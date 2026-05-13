import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output — smaller Docker/PM2 deployment, no unnecessary files
  output: "standalone",

  // Compress responses with gzip (Nginx also does this, but belt-and-suspenders)
  compress: true,

  // Aggressive image optimisation
  images: {
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 3600,
  },

  // Add long-lived cache headers for static assets and API responses
  async headers() {
    return [
      // Immutable static assets (_next/static) — cache for 1 year
      {
        source: "/_next/static/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
      // Favicons / public assets — cache for 24h
      {
        source: "/:file(favicon\\.ico|robots\\.txt|sitemap\\.xml)",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=86400, stale-while-revalidate=3600",
          },
        ],
      },
      // API proxy routes — let the FastAPI response headers win, but allow
      // the browser to revalidate without a full round-trip
      {
        source: "/api/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "no-store",
          },
        ],
      },
      // All pages — short browser cache with background revalidation
      {
        source: "/(.*)",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=0, must-revalidate",
          },
          // Security hardening
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },

  // Experimental: partial pre-rendering and optimised package imports
  experimental: {
    optimizePackageImports: [
      "lucide-react",
      "@radix-ui/react-icons",
      "recharts",
    ],
  },
};

export default nextConfig;
