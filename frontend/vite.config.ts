import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy /api/copilotkit to the CopilotKit Runtime during development
      "/api/copilotkit": {
        target: "http://localhost:3000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/copilotkit/, "/copilotkit"),
      },
    },
  },
  test: {
    // Vitest configuration
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      reporter: ["text", "json", "html"],
    },
  },
});
