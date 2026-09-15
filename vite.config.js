import { cp } from "node:fs/promises";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

const projectRoot = process.cwd();

const pagesBuild = {
  name: "pages-build",
  transformIndexHtml: {
    order: "pre",
    handler(html) {
      return html
        .replace(/\s*<script src="https:\/\/unpkg\.com\/react@[^\"]+"><\/script>/g, "")
        .replace(/\s*<script src="https:\/\/unpkg\.com\/react-dom@[^\"]+"><\/script>/g, "")
        .replace(/\s*<script src="https:\/\/unpkg\.com\/htm@[^\"]+"><\/script>/g, "")
        .replace(/\s*<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/@tailwindcss\/browser@4"><\/script>/g, "")
        .replace(/\s*<style type="text\/tailwindcss">[\s\S]*?<\/style>/, "")
        .replace('<script src="./app.js"></script>', '<script type="module" src="./build-entry.js"></script>');
    },
  },
  async closeBundle() {
    await cp(resolve(projectRoot, "docs/fonts"), resolve(projectRoot, "dist/fonts"), { recursive: true });
  },
};

export default defineConfig({
  root: "docs",
  base: "./",
  publicDir: false,
  plugins: [pagesBuild, tailwindcss()],
  build: {
    outDir: "../dist",
    emptyOutDir: true,
  },
});
