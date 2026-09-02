import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Garden from "../src/pages/Garden";
import type { WishCard } from "../src/api/types";

function card(id: string, trigger: string | null, state: WishCard["state"] = "wind"): WishCard {
  return {
    id,
    title: `愿望 ${id}`,
    original_text_excerpt: null,
    seeded_at: "2026-09-01T04:00:00Z",
    state,
    timing: {
      type: "season",
      label: "正在等待合适的风：冬天",
      trigger_kind: "time",
      next_trigger_at: trigger,
    },
    soft_deferred: false,
    degraded_reason: null,
    version: 1,
  };
}

// 服务端按 seeded_at 倒序返回；河流视图要重排成 next_trigger_at 升序
const WIND_ITEMS = [
  card("late", "2026-12-20T01:00:00Z"),
  card("none", null),
  card("soon", "2026-10-05T01:00:00Z"),
];

let calls: string[] = [];

function renderGarden(search: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/garden${search}`]}>
        <Garden />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function cardIds(): string[] {
  return screen
    .getAllByTestId("wish-card")
    .map((el) => el.getAttribute("data-wish-id") ?? "");
}

beforeEach(() => {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      calls.push(String(url));
      return new Response(JSON.stringify({ items: WIND_ITEMS, next_cursor: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("未发生之地：视图切换", () => {
  it("UT-S05-20: 切换视图不触发新请求", async () => {
    renderGarden("?state=wind");
    await waitFor(() => expect(cardIds()).toHaveLength(3));
    const before = calls.length;
    expect(before).toBe(1);

    await userEvent.click(screen.getByRole("button", { name: "河流" }));
    await waitFor(() => expect(cardIds()[0]).toBe("soon"));
    await userEvent.click(screen.getByRole("button", { name: "花园" }));

    // 两次切换之后请求计数不变——重排发生在浏览器内存里
    expect(calls.length).toBe(before);
  });

  it("ST-S05-02: 切到河流视图不丢失筛选，数据集不变且按 next_trigger_at 升序重排", async () => {
    renderGarden("?state=wind");
    await waitFor(() => expect(cardIds()).toEqual(["late", "none", "soon"]));
    expect(calls[0]).toContain("state=wind");
    const requests = calls.length;

    await userEvent.click(screen.getByRole("button", { name: "河流" }));

    await waitFor(() => expect(cardIds()).toEqual(["soon", "late", "none"]));
    // 筛选没有被重置：胶囊仍然停在「风来了」，也没有再打一次接口
    expect(screen.getByRole("button", { name: "风来了" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(calls.length).toBe(requests);
    expect(calls.every((url) => url.includes("state=wind"))).toBe(true);
  });
});
