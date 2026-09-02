import { describe, expect, it } from "vitest";
import { sortForRiver } from "../src/lib/river";

describe("河流视图排序", () => {
  it("UT-S05-19: 排序键为 next_trigger_at 升序，null 排最后", () => {
    const cards = [
      { id: "c", next_trigger_at: null },
      { id: "a", next_trigger_at: "2026-12-01T01:00:00Z" },
      { id: "d", next_trigger_at: null },
      { id: "b", next_trigger_at: "2026-10-01T01:00:00Z" },
    ];

    const sorted = sortForRiver(cards);

    expect(sorted.map((c) => c.id)).toEqual(["b", "a", "c", "d"]);
    // 原数组不被就地修改：花园视图与河流视图共用同一批数据，改一个会污染另一个
    expect(cards.map((c) => c.id)).toEqual(["c", "a", "d", "b"]);
  });

  it("非法时间戳按「没有时机」处理，不抛异常也不排到最前", () => {
    const sorted = sortForRiver([
      { id: "bad", next_trigger_at: "not-a-date" },
      { id: "ok", next_trigger_at: "2026-10-01T01:00:00Z" },
    ]);
    expect(sorted.map((c) => c.id)).toEqual(["ok", "bad"]);
  });
});
