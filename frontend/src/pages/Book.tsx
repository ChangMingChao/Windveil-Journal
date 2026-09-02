import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { MemoryListResponse } from "../api/types";

/** 已发生之书。`lived_pages` 是这个产品里唯一允许出现的计数——它数的是已经发生的事。 */
export default function Book() {
  const query = useQuery({
    queryKey: ["memories"],
    queryFn: () => api<MemoryListResponse>("/memories?limit=20"),
  });

  if (query.isPending) return <p className="text-ink-soft">正在翻开…</p>;
  const data = query.data;

  return (
    <main>
      <h1 className="text-[28px]">已发生之书</h1>
      <p className="mt-2 text-ink-soft">你已经活过的 {data?.lived_pages ?? 0} 页</p>

      {!data || data.items.length === 0 ? (
        <p className="mt-10 text-center text-ink-soft">
          还没有哪一页被收进来。发生了什么，随时来写下它。
        </p>
      ) : (
        <ul className="mt-6 flex flex-col gap-4">
          {data.items.map((memory) => (
            <li key={memory.id}>
              <Link
                to={`/book/${memory.id}`}
                className="flex gap-4 rounded-card border border-line bg-card p-4 shadow-card"
              >
                <span
                  aria-hidden="true"
                  className="w-10 shrink-0 rounded-[6px] bg-paper"
                  style={{
                    backgroundImage: memory.cover_media_id
                      ? undefined
                      : "repeating-linear-gradient(45deg,#E3DCCB 0 4px,transparent 4px 8px)",
                  }}
                />
                <span className="min-w-0">
                  <h2 className="text-[20px]">{memory.title}</h2>
                  <span className="mt-1 block text-[13px] text-ink-soft">
                    {memory.happened_from}
                    {memory.happened_to ? ` — ${memory.happened_to}` : ""}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
