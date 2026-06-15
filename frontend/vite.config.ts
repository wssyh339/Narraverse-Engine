import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

function packageName(id: string) {
  const marker = "node_modules/.pnpm/";
  if (id.includes(marker)) {
    const encoded = id.slice(id.indexOf(marker) + marker.length).split("/node_modules/")[0];
    const head = encoded.split("_")[0];
    if (head.startsWith("@")) {
      const scopeEnd = head.indexOf("+", 1);
      return scopeEnd > -1 ? `${head.slice(0, scopeEnd)}/${head.slice(scopeEnd + 1)}` : head.replace("+", "/");
    }
    return head.split("@")[0];
  }
  const plain = "node_modules/";
  if (id.includes(plain)) {
    const rest = id.slice(id.indexOf(plain) + plain.length);
    return rest.startsWith("@") ? rest.split("/").slice(0, 2).join("/") : rest.split("/")[0];
  }
  return "";
}

function intEnv(value: string | undefined, fallback: number) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  const frontendHost = process.env.FRONTEND_HOST || env.FRONTEND_HOST || "0.0.0.0";
  const frontendPort = intEnv(process.env.FRONTEND_PORT || env.FRONTEND_PORT, 5173);

  return {
    envDir: "..",
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) {
              return undefined;
            }
            const pkg = packageName(id);
            if (pkg === "echarts" || pkg === "zrender") {
              return "vendor-charts";
            }
            if (pkg === "refractor") {
              return "vendor-highlight";
            }
            if (
              pkg === "unified" ||
              pkg.startsWith("micromark") ||
              pkg.startsWith("mdast-util") ||
              pkg.startsWith("hast-util") ||
              pkg === "parse5" ||
              pkg.startsWith("remark-") ||
              pkg.startsWith("rehype-")
            ) {
              return "vendor-markdown-core";
            }
            if (pkg === "react-markdown" || pkg === "remark-gfm") {
              return "vendor-markdown-ui";
            }
            if (pkg === "@remix-run/router" || pkg === "react-router" || pkg === "react-router-dom") {
              return "vendor-router";
            }
            if (pkg === "@tanstack/query-core" || pkg === "@tanstack/react-query") {
              return "vendor-query";
            }
            if (pkg === "axios") {
              return "vendor-http";
            }
            if (pkg === "lucide-react") {
              return "vendor-lucide";
            }
            if (pkg === "react" || pkg === "react-dom" || pkg === "scheduler") {
              return "vendor-react";
            }
            return undefined;
          },
        },
      },
    },
    server: {
      host: frontendHost,
      port: frontendPort,
    },
    preview: {
      host: frontendHost,
      port: frontendPort,
    },
  };
});
