// 只放构建配置。测试配置在 vitest.config.ts —— 两边分开是刻意的：
// vitest 自带一份嵌套的 vite，在同一个文件里同时 import 两边的 defineConfig
// 会让 tsc 认为 Plugin 是两个互不兼容的类型。
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

// 静态产物落在 frontend/dist（部署方案 §4.2）。
// manifest 与 service worker 必须可取——SMOKE-core-16 逐个 GET 它们。
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      filename: "sw.js",
      manifestFilename: "manifest.webmanifest",
      manifest: {
        name: "未发生事件管理局",
        short_name: "未发生",
        description: "一个存放还没发生的事的地方",
        lang: "zh-CN",
        start_url: "/",
        display: "standalone",
        background_color: "#FDFBF7",
        theme_color: "#FDFBF7",
        icons: [
          { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" },
        ],
      },
      workbox: {
        // 离线只兜静态外壳。愿望内容一律不进 Cache Storage：
        // 一个主打私密的应用不该把用户写的话留在磁盘缓存里，
        // 所以这里没有任何 runtimeCaching 规则。
        globPatterns: ["**/*.{js,css,html,svg,webmanifest}"],
        navigateFallback: "index.html",
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
