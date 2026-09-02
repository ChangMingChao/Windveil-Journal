import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { WishListResponse, WishState } from "../api/types";
import { orderFor, type GardenView } from "../lib/river";

const STATES: { value: "all" | WishState; label: string; empty: string }[] = [
  { value: "all", label: "全部", empty: "这里还什么都没有。想到什么，随时来种下它。" },
  { value: "seeded", label: "刚种下", empty: "还没有刚种下的。" },
  { value: "brewing", label: "正在酝酿", empty: "还没有正在酝酿的。不着急。" },
  { value: "wind", label: "风来了", empty: "风还没来。" },
  { value: "going", label: "正在发生", empty: "还没有什么正在发生。不着急。" },
  { value: "happened", label: "已经发生", empty: "还没有已经发生的。" },
  { value: "let_go", label: "安静放下", empty: "还没有被放下的。" },
];

function isState(raw: string | null): raw is "all" | WishState {
  return STATES.some((s) => s.value === raw);
}

export default function Garden() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("state");
  const state = isState(raw) ? raw : "all";
  // 视图是纯前端状态，刻意不进 URL：它不影响拿到的数据，只影响排序
  const [view, setView] = useState<GardenView>("garden");

  const query = useQuery({
    queryKey: ["wishes", state],
    queryFn: () => api<WishListResponse>(`/wishes?state=${state}&limit=20`),
  });

  const items = useMemo(() => orderFor(query.data?.items ?? [], view), [query.data, view]);
  const current = STATES.find((s) => s.value === state)!;

  return (
    <main>
      <h1 className="text-[28px]">未发生之地</h1>

      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="按状态筛选">
        {STATES.map((s) => (
          <button
            key={s.value}
            type="button"
            aria-pressed={s.value === state}
            onClick={() => setParams(s.value === "all" ? {} : { state: s.value })}
            className={`min-h-[44px] rounded-[999px] border px-4 text-[13px] ${
              s.value === state
                ? "border-clay bg-clay text-paper"
                : "border-line bg-card text-ink-soft"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="mt-4 flex gap-2" role="group" aria-label="切换视图">
        {(["garden", "river"] as const).map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={view === v}
            onClick={() => setView(v)}
            className={`min-h-[44px] rounded-[999px] border px-4 text-[13px] ${
              view === v ? "border-mist-deep text-mist-deep" : "border-line text-ink-soft"
            }`}
          >
            {v === "garden" ? "花园" : "河流"}
          </button>
        ))}
      </div>

      {query.isPending ? (
        <p className="mt-8 text-ink-soft" aria-busy="true">
          正在把它们取回来…
        </p>
      ) : items.length === 0 ? (
        <section className="mt-10 text-center">
          <p className="text-ink-soft">{current.empty}</p>
          {state === "all" && (
            <Link
              to="/welcome"
              className="mt-6 inline-flex min-h-[44px] items-center rounded-[999px] bg-clay px-6 text-paper"
            >
              种下
            </Link>
          )}
        </section>
      ) : (
        <ul
          data-testid="wish-list"
          className={
            view === "garden"
              ? "mt-6 grid grid-cols-2 gap-4"
              : "mt-6 flex flex-col gap-3 border-l border-line pl-4"
          }
        >
          {items.map((wish, index) => (
            <li
              key={wish.id}
              data-testid="wish-card"
              data-wish-id={wish.id}
              className={view === "garden" && index % 2 === 1 ? "mt-6" : undefined}
            >
              <Link
                to={`/wish/${wish.id}`}
                className="block rounded-card border border-line bg-card p-4 shadow-card"
              >
                <h2 className="text-[20px]">{wish.title}</h2>
                <p className="mt-2 text-[13px] text-ink-soft">{wish.timing.label}</p>
                {wish.soft_deferred && (
                  <p className="mt-1 text-[13px] text-mist-deep">它会在下一周再来找你</p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
