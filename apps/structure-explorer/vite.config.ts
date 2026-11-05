import { copyFileSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// Preserve the published viewer's third-party notices inside the single bundle.
const license = readFileSync(
  new URL("./node_modules/pdbe-molstar/build/pdbe-molstar-plugin.js.LICENSE.txt", import.meta.url), "utf8",
) + "\n" + readFileSync(new URL("./node_modules/molstar-mvs/LICENSE", import.meta.url), "utf8");

export default defineConfig(({ mode }) => ({
  resolve: {
    // The viewer does not expose MP4 export in the MCP App; its bundled
    // Emscripten encoder fetches a data: URL, which the host CSP blocks.
    alias: {
      "h264-mp4-encoder": fileURLToPath(new URL("./src/h264-mp4-encoder-stub.ts", import.meta.url)),
    },
  },
  plugins: [viteSingleFile(), {
    name: "workspace-resource-aliases",
    writeBundle(options) {
      if (mode === "smoke") return;
      const directory = options.dir ?? fileURLToPath(new URL("../../pdbe_mcp_server/ui/", import.meta.url));
      const source = resolve(directory, "workspace.html");
      for (const name of ["structure-explorer.html", "structure-comparison.html", "mvs-viewer.html"]) {
        copyFileSync(source, resolve(directory, name));
      }
    },
  }],
  build: {
    rollupOptions: {
      input: mode === "smoke" ? "tests/mvs-host.html" : "workspace.html",
      output: { banner: `/*! ${license.replaceAll("*/", "* /")} */` },
    },
    outDir: fileURLToPath(new URL("../../pdbe_mcp_server/ui", import.meta.url)),
    emptyOutDir: false,
  },
}));
