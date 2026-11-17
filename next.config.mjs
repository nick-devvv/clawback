/** @type {import('next').NextConfig} */

// /api/py/* goes to the Python API: uvicorn on :8001 in dev, the api/index.py function on Vercel.
// (Cognee's own server also likes :8000, so the API sits on :8001.)
// The site pages are built from the design boards (design/build_site.py -> public/site/*.html):
//   /      landing   /demo   watch it   /live   try it live (calls /api/py)   /console   plain dev screen
const nextConfig = {
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/", destination: "/site/landing.html" },
        { source: "/demo", destination: "/site/demo.html" },
        { source: "/live", destination: "/site/live.html" },
      ],
      afterFiles: [
        {
          source: "/api/py/:path*",
          destination: process.env.NODE_ENV === "development" ? "http://127.0.0.1:8001/api/py/:path*" : "/api/",
        },
      ],
    };
  },
};

export default nextConfig;
