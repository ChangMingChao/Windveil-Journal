import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// 测试跑在 jsdom 里，不走 PWA / Tailwind 插件——它们对断言没有贡献，只拖慢启动。
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    reporters: ["default", "./tests/helpers/reporter.ts"],
  },
});
