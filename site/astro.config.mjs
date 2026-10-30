import { defineConfig } from "astro/config";

// Served from GitHub Pages on the custom domain nabd.duraym.com (DNS: CNAME nabd -> moaddreem.github.io).
export default defineConfig({
  site: "https://nabd.duraym.com",
  trailingSlash: "ignore",
});
