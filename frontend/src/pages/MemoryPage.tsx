import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Memory } from "../api/types";

const MOODS = [
  { value: "relieved", label: "松了口气" },
  { value: "healed", label: "被治愈" },
  { value: "tearful", label: "有点想哭" },
  { value: "calm", label: "很平静" },
  { value: "proud", label: "有点骄傲" },
  { value: "unspeakable", label: "说不出来" },
] as const;

/** 记忆页：草稿态可编辑，已发布是阅读态。全部区块都可以留空（ST-S06-02）。 */
export default function MemoryPage() {
  const { memoryId } = useParams<{ memoryId: string }>();
  const client = useQueryClient();
  const [draft, setDraft] = useState<Partial<Memory>>({});

  const query = useQuery({
    queryKey: ["memory", memoryId],
    queryFn: () => api<Memory>(`/memories/${memoryId}`),
    enabled: Boolean(memoryId),
  });

  useEffect(() => {
    if (query.data) setDraft({});
  }, [query.data?.id, query.data]);

  const save = useMutation({
    mutationFn: async (patch: Partial<Memory>) =>
      api<Memory>(`/memories/${memoryId}`, { method: "PATCH", json: patch }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["memory", memoryId] }),
  });

  const publish = useMutation({
    mutationFn: async () =>
      api<{ memory: Memory }>(`/memories/${memoryId}/publish`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["memory", memoryId] });
      void client.invalidateQueries({ queryKey: ["memories"] });
    },
  });

  if (query.isPending) return <p className="text-ink-soft">正在翻到这一页…</p>;
  if (query.isError) return <p className="text-ink-soft">这一页已经不在书里了。</p>;
  const memory = query.data;
  const editable = memory.status === "draft";
  const value = <K extends keyof Memory>(key: K): Memory[K] =>
    (draft[key] ?? memory[key]) as Memory[K];

  return (
    <main className="rounded-card bg-card p-5 shadow-card">
      {editable ? (
        <input
          aria-label="这一页的标题"
          value={String(value("title") ?? "")}
          maxLength={80}
          onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
          className="w-full rounded-input border border-line bg-paper px-3 py-2 font-heading text-[28px]"
        />
      ) : (
        <h1 className="text-[28px]">{memory.title}</h1>
      )}

      <p className="mt-2 text-[13px] text-ink-soft">
        {memory.happened_from}
        {memory.happened_to ? ` — ${memory.happened_to}` : ""}
      </p>
      {memory.note_before_seeded && (
        <p className="text-[13px] text-ink-soft">你是在它发生之后才写下它的。</p>
      )}

      {(["cause", "process"] as const).map((field) => (
        <section key={field} className="mt-6">
          <h2 className="text-[20px]">{field === "cause" ? "起因" : "经过"}</h2>
          {editable ? (
            <textarea
              aria-label={field === "cause" ? "起因" : "经过"}
              rows={field === "cause" ? 3 : 6}
              maxLength={field === "cause" ? 2000 : 4000}
              value={String(value(field) ?? "")}
              onChange={(e) => setDraft((d) => ({ ...d, [field]: e.target.value }))}
              className="mt-2 w-full rounded-input border border-line bg-paper p-3"
              placeholder={field === "process" ? "这里可以写写它是怎么发生的" : undefined}
            />
          ) : (
            <p className="mt-2 whitespace-pre-wrap text-ink-soft">
              {memory[field] ?? (field === "process" ? "这里可以写写它是怎么发生的" : "")}
            </p>
          )}
        </section>
      ))}

      <section className="mt-6">
        <h2 className="text-[20px]">当时的心情</h2>
        <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="当时的心情">
          {MOODS.map((mood) => (
            <button
              key={mood.value}
              type="button"
              disabled={!editable}
              aria-pressed={value("mood") === mood.value}
              onClick={() =>
                setDraft((d) => ({ ...d, mood: value("mood") === mood.value ? null : mood.value }))
              }
              className={`min-h-[44px] rounded-[999px] border px-4 text-[13px] ${
                value("mood") === mood.value
                  ? "border-sprout-deep text-sprout-deep"
                  : "border-line text-ink-soft"
              }`}
            >
              {mood.label}
            </button>
          ))}
        </div>
      </section>

      <section className="mt-6">
        <h2 className="text-[20px]">如果只留一句话</h2>
        {editable ? (
          <textarea
            aria-label="如果只留一句话"
            rows={2}
            maxLength={300}
            value={String(value("last_line") ?? "")}
            onChange={(e) => setDraft((d) => ({ ...d, last_line: e.target.value }))}
            className="mt-2 w-full rounded-input border border-line bg-paper p-3"
          />
        ) : (
          <p className="mt-2 italic text-ink-soft">{memory.last_line ?? ""}</p>
        )}
      </section>

      <div className="mt-8 flex flex-wrap gap-3">
        <button
          type="button"
          disabled={Object.keys(draft).length === 0}
          onClick={() => save.mutate(draft)}
          className="min-h-[44px] rounded-[999px] border border-line px-5 disabled:opacity-50"
        >
          先保存
        </button>
        {editable && (
          <button
            type="button"
            onClick={() => publish.mutate()}
            className="min-h-[44px] rounded-[999px] bg-clay px-6 text-paper"
          >
            收进书里
          </button>
        )}
      </div>
    </main>
  );
}
