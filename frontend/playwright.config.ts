import path from "node:path";
import { defineConfig } from "@playwright/test";

const python =
  process.platform === "win32"
    ? path.join(".venv", "Scripts", "python.exe")
    : path.join(".venv", "bin", "python");

// End-to-end against both real servers: the backend from its venv, the frontend's
// production build (run `npm run build` first). One worker keeps the run within the
// API rate limit (spec §11).
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  workers: 1,
  use: { baseURL: "http://localhost:3000", trace: "retain-on-failure" },
  webServer: [
    {
      command: `${python} -m uvicorn nfa_studio.api.app:app --port 8000`,
      cwd: "../backend",
      url: "http://127.0.0.1:8000/v1/health",
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: "npm run start",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
