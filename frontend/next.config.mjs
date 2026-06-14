/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    // proxy API calls to the FastAPI backend in dev so the browser sees same-origin
    const api = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};
export default nextConfig;
