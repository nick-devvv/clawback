/** @type {import('next').NextConfig} */

// /api/py/* goes to the Python API: uvicorn on :8001 in dev, the api/index.py function on Vercel.
// (Cognee's own server also likes :8000, so the API sits on :8001.)
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/py/:path*",
        destination: process.env.NODE_ENV === "development" ? "http://127.0.0.1:8001/api/py/:path*" : "/api/",
      },
    ];
  },
};

export default nextConfig;
