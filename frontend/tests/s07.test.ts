import { describe, expect, it } from "vitest";
import { canRecall, RECALL_COPY } from "../src/lib/recall";

describe("S07 唤回交互契约", () => {
  it("UT-S07-18: 重新种下只面向 let_go", () => {
    expect(canRecall("let_go")).toBe(true);
    for (const state of ["seeded", "brewing", "wind", "going", "happened"] as const) {
      expect(canRecall(state)).toBe(false);
    }
  });
  it("UT-S07-19: 再放一会儿是关闭动作", () => {
    expect(RECALL_COPY.secondary).toBe("再放一会儿");
  });
  it("UT-S07-20: 成功文案不含禁用词", () => {
    for (const word of ["放弃", "未完成", "失败", "逾期", "完成率"]) {
      expect(RECALL_COPY.success).not.toContain(word);
    }
  });
});
