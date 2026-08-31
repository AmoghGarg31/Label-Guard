/** @type {import('next').NextConfig} */
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
const isDevelopment = process.env.NODE_ENV !== 'production';
const scriptSources = ["'self'", "'unsafe-inline'", ...(isDevelopment ? ["'unsafe-eval'"] : [])].join(' ');
const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'no-referrer' },
  { key: 'Permissions-Policy', value: 'camera=(self), microphone=(), geolocation=()' },
  {
    key: 'Content-Security-Policy',
    value: `default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; form-action 'self'; script-src ${scriptSources}; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data: ${apiBase}; connect-src 'self' ${apiBase}`,
  },
];

const nextConfig = {
  poweredByHeader: false,
  outputFileTracingRoot: __dirname,
  async headers() { return [{ source: '/(.*)', headers: securityHeaders }]; },
};

module.exports = nextConfig;
