/** S09「先记一下」：P1 主输入下方的轻事件区。

规格来源：core-06-lite-events-design.md。三条铁律：
  1. 零摩擦：一句话、无 Agent、无追问；空内容禁用「记下」（双层防御的前端层）。
  2. 无压力：不显示条数、时间戳或任何提醒开关——划掉就完了。
  3. 隔离：轻事件与愿望完全互不影响；不进未发生之地、不进已发生之书。
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { LiteEvent } from "../api/types";

const COPY = {
  entry: "先记一下",
  inputPlaceholder: "想到什么小事，一句话记下它",
  record: "记下",
  done: "划掉了",
  dismiss: "收走",
  hint: "记下的事，划掉就完了。",
  emptyGuide: "想到什么小事，一句话记下它",
} as const;

export default function LiteEvents() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");

  const list = useQuery({
    queryKey: ["lite-events", open],
    // 展开时才取数；收起不请求（列表区域不占视觉空间，也不占请求）
    enabled: open,
    queryFn: () => api<{ items: LiteEvent[] }>("/lite-events"),
  });

  const record = useMutation({
    mutationFn: async () =>
      api<LiteEvent>("/lite-events", { method: "POST", json: { text: text.trim() } }),
    onSuccess: () => {
      setText("");
      void client.invalidateQueries({ queryKey: ["lite-events"] });
    },
  });

  const markDone = useMutation({
    mutationFn: async (id: string) => api<LiteEvent>(`/lite-events/${id}/done`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["lite-events"] }),
  });

  const remove = useMutation({
    mutationFn: async (id: string) => api<void>(`/lite-events/${id}`, { method: "DELETE" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["lite-events"] }),
  });

  const canSave = text.trim().length > 0 && !record.isPending;
  const items = (list.data?.items ?? []).slice(0, 8);

  return (
    <section className="mt-10">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="min-h-[44px] text-[13px] text-clay underline underline-offset-4"
      >
        {open ? "▾" : "▸"} {COPY.entry}
      </button>

      {open && (
        <div className="mt-3">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={200}
            placeholder={COPY.emptyGuide}
            aria-label={COPY.entry}
            className="min-h-[48px] w-full rounded-input border border-line bg-white px-4"
          />
          <button
            type="button"
            onClick={() => record.mutate()}
            disabled={!canSave}
            className="mt-2 min-h-[44px] rounded-[999px] border border-line px-5 text-clay disabled:opacity-50"
          >
            {COPY.record}
          </button>

          {items.length === 0 && (
            <p className="mt-3 text-[13px] text-ink-soft">{COPY.hint}</p>
          )}

          <ul className="mt-2 flex flex-col gap-2">
            {items.map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-[14px] border border-line bg-card px-4 py-2"
              >
                <span className="text-[15px]">{item.text}</span>
                <span className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => markDone.mutate(item.id)}
                    className="min-h-[40px] text-[13px] text-clay underline underline-offset-4"
                  >
                    {COPY.done}
                  </button>
                  <button
                    type="button"
                    onClick={() => remove.mutate(item.id)}
                    className="min-h-[40px] text-[13px] text-ink-soft underline underline-offset-4"
                  >
                    {COPY.dismiss}
                  </button>
                </span>
              </li>
            ))}
          </ul>

          {items.length > 0 && <p className="mt-3 text-[13px] text-ink-soft">{COPY.hint}</p>}
        </div>
      )}
    </section>
  );
}
