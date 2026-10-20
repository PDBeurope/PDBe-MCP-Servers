import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// Preserve the published viewer's third-party notices inside the single bundle.
const license = readFileSync(
  new URL("./node_modules/pdbe-molstar/build/pdbe-molstar-plugin.js.LICENSE.txt", import.meta.url), "utf8",
) + "\n" + readFileSync(new URL("./node_modules/molstar/LICENSE", import.meta.url), "utf8");

export default defineConfig(({ mode }) => ({
  plugins: [viteSingleFile()],
  build: {
    rollupOptions: {
      input: mode === "comparison" ? "structure-comparison.html" : "structure-explorer.html",
      output: { banner: `/*! ${license.replaceAll("*/", "* /")} */` },
    },
    outDir: fileURLToPath(new URL("../../pdbe_mcp_server/ui", import.meta.url)),
    emptyOutDir: false,
  },
}));
