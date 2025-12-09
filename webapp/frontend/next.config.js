/** @type {import('next').NextConfig} */
const nextConfig = {
  skipTrailingSlashRedirect: true,
  async rewrites() {
    // In Docker, use the service name 'backend'
    const backendHost = process.env.BACKEND_HOST || 'backend'
    const backendPort = process.env.BACKEND_PORT || '8067'
    const apiBase = `http://${backendHost}:${backendPort}`
    
    return {
      beforeFiles: [
        // Handle /api/ root
        {
          source: '/api',
          destination: `${apiBase}/api`,
        },
        // Handle /api/* paths (with and without trailing slashes)
        {
          source: '/api/:path*',
          destination: `${apiBase}/api/:path*`,
        },
        {
          source: '/media/:path*',
          destination: `${apiBase}/media/:path*`,
        },
      ],
    }
  },
}

module.exports = nextConfig