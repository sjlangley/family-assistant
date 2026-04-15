import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "src/setupTests.ts",
    server: {
      deps: {
        // Inline ESM-only markdown processing packages so Vitest/jsdom can handle them
        inline: [
          /^react-markdown/,
          /^remark-/,
          /^rehype-/,
          /^micromark/,
          /^mdast-/,
          /^hast-/,
          /^unist-/,
          /^vfile/,
          /^unified/,
          /^bail$/,
          /^is-plain-obj$/,
          /^trough$/,
          /^decode-named-character-reference$/,
          /^ccount$/,
          /^devlop$/,
          /^escape-string-regexp$/,
          /^property-information$/,
          /^space-separated-tokens$/,
          /^comma-separated-tokens$/,
          /^hastscript$/,
          /^html-void-elements$/,
          /^zwitch$/,
          /^trim-lines$/,
        ],
      },
    },
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html", "lcov"],
      exclude: [
        "**/*.config.*",
        "**/main.tsx",
        "**/setupTests.ts",
        "**/vite-env.d.ts",
        "**/*.d.ts",
        "**/node_modules/**",
        "**/dist/**",
      ],
    },
  },
});
