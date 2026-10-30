import { defineConfig } from "astro/config";

// Served from GitHub Pages on the custom domain nabd.durayim.com (DNS: CNAME nabd -> moaddreem.github.io).
export default defineConfig({
  site: "https://nabd.durayim.com",
  trailingSlash: "ignore",
});
