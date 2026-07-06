import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Scope build traces to this app so a stray lockfile in a parent directory
  // doesn't make Next infer the wrong workspace root.
  outputFileTracingRoot: __dirname,
};

export default nextConfig;
