import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { WishDetail } from "../api/types";
import { canRecall, RECALL_COPY } from "../lib/recall";
import { PROPOSAL_COPY, proposalLabel, tierOf } from "../lib/remembered";
import type { TimingProposal } from "../api/types";

/** 整理半屏的 5 个动作，按侵入性递增排列（S05.2 Step 15）。 */
const TIDY_ACTIONS = [
  { key: "amend", label: "改一改它" },
  { key: "pause", label: "暂时不提醒" },
  { key: "back", label: "退回酝酿" },
  { key: "let_go", label: "安静放下" },
  { key: "delete", label: "彻底删除" },
] as const;

export default function WishDetailPage() {
  const { wishId } = useParams<{ wishId: string }>();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [tidyOpen, setTidyOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [title, setTitle] = useState("");

  const detail = useQuery({
    queryKey: ["wish", wishId],
    queryFn: () => api<WishDetail>(`/wishes/${wishId}`),
    enabled: Boolean(wishId),
  });

  const act = useMutation({
    mutationFn: async (path: string) => api<WishDetail>(`/wishes/${wishId}${path}`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["wish", wishId] });
      void client.invalidateQueries({ queryKey: ["wishes"] });
      setTidyOpen(false);
    },
  });

  const amend = useMutation({
    mutationFn: async () =>
      api<WishDetail>(`/wishes/${wishId}`, { method: "PATCH", json: { title } }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["wish", wishId] });
      void client.invalidateQueries({ queryKey: ["wishes"] });
      setTidyOpen(false);
    },
  });

  const remove = useMutation({
    mutationFn: async () =>
      api<void>(`/wishes/${wishId}?confirm=true`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["wishes"] });
      navigate("/garden");
    },
  });

  const recall = useMutation({
    mutationFn: async () =>
      api<WishDetail>(`/wishes/${wishId}/recall`, { method: "POST" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["wish", wishId] });
      void client.invalidateQueries({ queryKey: ["wishes"] });
    },
  });

  // S03 时机提议分支（S08）：模型只提议，确认前不产生任何提醒
  const [adviceDegraded, setAdviceDegraded] = useState(false);

  const propose = useMutation({
    mutationFn: async () =>
      api<{ proposal: TimingProposal | null; degraded: boolean }>(
        `/wishes/${wishId}/timing-proposals`,
        { method: "POST" },
      ),
    onSuccess: (result) => {
      setAdviceDegraded(result.degraded || result.proposal === null);
      void client.invalidateQueries({ queryKey: ["wish", wishId] });
    },
    onError: () => setAdviceDegraded(true),
  });

  const confirmProposal = useMutation({
    mutationFn: async (proposalId: string) =>
      api<unknown>(`/wishes/${wishId}/timing-proposals/${proposalId}/confirm`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["wish", wishId] }),
  });

  const rejectProposal = useMutation({
    mutationFn: async (proposalId: string) =>
      api<unknown>(`/wishes/${wishId}/timing-proposals/${proposalId}/reject`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["wish", wishId] }),
  });

  const happened = useMutation({
    mutationFn: async (happened_from: string) =>
      api<{ memory: { id: string } }>(`/wishes/${wishId}/happened`, {
        method: "POST",
        json: { happened_from },
      }),
    onSuccess: (result) => navigate(`/book/${result.memory.id}`),
  });

  if (detail.isPending) return <p className="text-ink-soft">正在打开…</p>;
  if (detail.isError) return <p className="text-ink-soft">这件事已经不在这里了。</p>;
  const wish = detail.data;
  const terminal = wish.state === "happened";
  const recallAvailable = canRecall(wish.state);

  return (
    <main>
      <h1 className="text-[28px]">{wish.title}</h1>
      <p className="mt-2 text-[13px] text-ink-soft">{wish.timing.label}</p>

      {wish.state === "seeded" && !wish.timing_proposal && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => propose.mutate()}
            disabled={propose.isPending}
            className="min-h-[44px] text-[14px] text-clay underline underline-offset-4 disabled:opacity-50"
          >
            {propose.isPending ? PROPOSAL_COPY.thinking : PROPOSAL_COPY.entry}
          </button>
          {adviceDegraded && (
            <p className="mt-2 text-[13px] text-ink-soft">{PROPOSAL_COPY.degraded}</p>
          )}
        </div>
      )}

      {wish.timing_proposal?.status === "pending" && (
        <section className="mt-6 rounded-card border border-line bg-card p-4 shadow-lamp">
          <h2 className="text-[18px]">
            它想了个时候：{proposalLabel(wish.timing_proposal.timing_type, wish.timing_proposal.timing_value)}
          </h2>
          {wish.timing_proposal.reason && (
            <p className="mt-2 text-[14px] text-ink-soft">
              {PROPOSAL_COPY.because}
              {wish.timing_proposal.reason}
            </p>
          )}
          <p className="mt-2 text-[13px] text-ink-soft">
            <span className="rounded-full border border-line px-2 py-0.5">
              {tierOf(wish.timing_proposal.confidence)}
            </span>
          </p>
          <p className="mt-2 text-[12px] text-ink-soft">定下来之前，它不会提醒你，也不会改变这张卡片的状态。</p>
          <div className="mt-3 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => confirmProposal.mutate(wish.timing_proposal!.id)}
              disabled={confirmProposal.isPending}
              className="min-h-[44px] rounded-[999px] bg-clay px-5 text-paper disabled:opacity-50"
            >
              {PROPOSAL_COPY.confirm}
            </button>
            <button
              type="button"
              onClick={() => rejectProposal.mutate(wish.timing_proposal!.id)}
              disabled={rejectProposal.isPending}
              className="min-h-[44px] rounded-[999px] border border-line px-5 text-clay disabled:opacity-50"
            >
              {PROPOSAL_COPY.reject}
            </button>
          </div>
        </section>
      )}
      {wish.let_go_at && (
        <p className="mt-1 text-[13px] text-ink-soft">安静放下于 {new Date(wish.let_go_at).toLocaleDateString("zh-CN")}</p>
      )}
      {wish.original_text && (
        <blockquote className="mt-4 border-l-2 border-line pl-4 italic text-ink-soft">
          {wish.original_text}
        </blockquote>
      )}
      {wish.amended_from && (
        <p className="mt-2 text-[13px] text-ink-soft">你最初写的是：{wish.amended_from}</p>
      )}

      {wish.current_step && (
        <section className="mt-8 rounded-card border border-line bg-card p-4 shadow-lamp">
          <h2 className="text-[20px]">下一小步</h2>
          <p className="mt-2">{String(wish.current_step["text"])}</p>
        </section>
      )}

      {wish.timeline.length > 0 && (
        <section className="mt-8">
          <h2 className="text-[20px]">准备过程</h2>
          <ol className="mt-3 flex flex-col gap-2 border-l border-line pl-4">
            {wish.timeline.map((entry) => (
              <li key={entry.id} className="text-ink-soft">
                {entry.text}
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="mt-10 flex flex-wrap gap-3">
        {recallAvailable && (
          <button
            type="button"
            onClick={() => recall.mutate()}
            disabled={recall.isPending}
            className="min-h-[44px] rounded-[999px] bg-clay px-5 text-paper disabled:opacity-50"
          >
            {recall.isPending ? "正在回来…" : RECALL_COPY.primary}
          </button>
        )}
        <button
          type="button"
          onClick={() => setTidyOpen(true)}
          className="min-h-[44px] rounded-[999px] border border-line px-5"
        >
          整理一下
        </button>
        {!terminal && (
          <button
            type="button"
            onClick={() => happened.mutate(new Date().toISOString().slice(0, 10))}
            className="min-h-[44px] rounded-[999px] bg-clay px-5 text-paper"
          >
            它已经发生了
          </button>
        )}
      </div>

      {recallAvailable && tidyOpen && (
        <section
          role="dialog"
          aria-label="重新种下"
          className="mt-6 rounded-card border border-line bg-card p-4"
        >
          <p className="text-ink-soft">这件事会回到「刚种下」，之后可以重新约定它的时机。</p>
          <div className="mt-4 flex gap-3">
            <button
              type="button"
              onClick={() => recall.mutate()}
              className="min-h-[44px] rounded-[999px] bg-clay px-5 text-paper"
            >
              {RECALL_COPY.primary}
            </button>
            <button
              type="button"
              onClick={() => setTidyOpen(false)}
              className="min-h-[44px] rounded-[999px] border border-line px-5"
            >
              {RECALL_COPY.secondary}
            </button>
          </div>
        </section>
      )}

      {!recallAvailable && tidyOpen && (
        <section
          role="dialog"
          aria-label="整理一下"
          className="mt-6 rounded-card border border-line bg-card p-4"
        >
          <ul className="flex flex-col gap-2">
            {TIDY_ACTIONS.filter(
              // 终态只留「彻底删除」——其余动作对已经发生的事没有意义（EX-17.1）
              (action) => !terminal || action.key === "delete",
            ).map((action) => (
              <li key={action.key}>
                {action.key === "amend" ? (
                  <div className="flex gap-2">
                    <input
                      aria-label="改一改它"
                      value={title}
                      maxLength={60}
                      onChange={(e) => setTitle(e.target.value)}
                      className="min-h-[44px] flex-1 rounded-input border border-line bg-paper px-3"
                      placeholder={wish.title}
                    />
                    <button
                      type="button"
                      disabled={!title.trim()}
                      onClick={() => amend.mutate()}
                      className="min-h-[44px] rounded-[999px] border border-line px-4 disabled:opacity-50"
                    >
                      保存
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      if (action.key === "delete") setConfirmDelete(true);
                      else if (action.key === "pause") act.mutate("/pause");
                      else if (action.key === "back") act.mutate("/back-to-brewing");
                      else act.mutate("/let-go");
                    }}
                    className="min-h-[44px] w-full rounded-input border border-line px-4 text-left"
                  >
                    {action.label}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {confirmDelete && (
        <section
          role="dialog"
          aria-label="彻底删除"
          className="mt-4 rounded-card border border-clay bg-card p-4"
        >
          <p className="text-ink-soft">
            「安静放下」可以随时再回来；「彻底删除」不可恢复，也不提供撤销。
          </p>
          <div className="mt-4 flex gap-3">
            {/* 默认焦点在取消：不可恢复的动作不该被顺手点掉（ST-S05-16 [manual]） */}
            <button
              type="button"
              autoFocus
              onClick={() => setConfirmDelete(false)}
              className="min-h-[44px] rounded-[999px] border border-line px-5"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => remove.mutate()}
              className="min-h-[44px] rounded-[999px] bg-clay px-5 text-paper"
            >
              仍然彻底删除
            </button>
          </div>
        </section>
      )}
    </main>
  );
}
