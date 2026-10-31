import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));

test("regression: dev server resolves the '@/src/...' imports used by the app entry", async () => {
  // `vite build` resolved these, but `npm run dev` answered /src/main.tsx with HTTP 500
  // ("Failed to resolve import \"@/src/app/App\"") because the alias only existed in tsconfig.
  const cacheDir = mkdtempSync(join(tmpdir(), "emergent-life-vite-"));
  const server = await createServer({
    root,
    configFile: join(root, "vite.config.ts"),
    cacheDir,
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true, include: [] },
    server: { middlewareMode: true, hmr: false, ws: false }
  });

  try {
    for (const url of ["/src/main.tsx", "/src/app/App.tsx", "/src/utils/encoding.ts"]) {
      const result = await server.transformRequest(url);
      assert.ok(result, `${url} did not transform`);
      assert.doesNotMatch(result.code, /from "@\//, `${url} still imports an unresolved '@/' path`);
    }
  } finally {
    await server.close();
    rmSync(cacheDir, { recursive: true, force: true });
  }
});
