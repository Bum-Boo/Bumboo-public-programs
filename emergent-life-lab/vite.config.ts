import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  // Mirror the tsconfig "@/*" path so `npm run dev` resolves "@/src/..." imports, not only `vite build`.
  resolve: {
    alias: [{ find: /^@\//, replacement: fileURLToPath(new URL("./", import.meta.url)) }]
  },
  server: { host: "127.0.0.1" },
  preview: { host: "127.0.0.1" }
});
