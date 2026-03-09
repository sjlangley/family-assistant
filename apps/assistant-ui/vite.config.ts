import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "src/setupTests.ts",
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html"],
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
