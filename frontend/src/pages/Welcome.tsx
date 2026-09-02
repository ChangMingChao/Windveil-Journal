import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { WishDetail } from "../api/types";

/** S01 首次体验 + 随手种下。三道温柔的问题可以整段跳过（Step 8 / EX-12.1）。 */
const QUESTIONS = [
  { key: "q1", prompt: "最近有什么，是你一直想做但还没做的？" },
  { key: "q2", prompt: "如果有一整天完全属于你，你会去哪里？" },
  { key: "q3", prompt: "有什么事，你希望它在今年内发生？" },
] as const;

export default function Welcome() {
  const navigate = useNavigate();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [text, setText] = useState("");
  const [question, setQuestion] = useState<string | null>(null);
  const [degraded, setDegraded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submitAnswers(skip: boolean): Promise<void> {
    const payload = skip
      ? []
      : QUESTIONS.filter((q) => (answers[q.key] ?? "").trim()).map((q) => ({
          question_key: q.key,
          answer_text: answers[q.key],
        }));
    // 写入失败也返回 204：初始记忆是增强项，不为它中断首次体验（EX-10.1）
    await api<void>("/onboarding/answers", { method: "POST", json: { answers: payload } });
  }

  async function seed(): Promise<void> {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await submitAnswers(false);
      const result = await api<{ wish: WishDetail; question: string | null; degraded: boolean }>(
        "/wishes",
        { method: "POST", json: { source: "text", text } },
      );
      setQuestion(result.question);
      setDegraded(result.degraded);
      setText("");
      if (!result.question) navigate("/garden");
    } catch {
      setError("这句话暂时没能存下来。它还在这里，再试一次就好。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1 className="text-[28px]">这里存放还没发生的事</h1>
      <p className="mt-2 text-ink-soft">不用现在做任何事。想到什么，写下来就好。</p>

      <section className="mt-8">
        <h2 className="text-[20px]">先聊三句（可以整段跳过）</h2>
        <ul className="mt-4 flex flex-col gap-4">
          {QUESTIONS.map((q) => (
            <li key={q.key}>
              <label htmlFor={q.key} className="block text-ink-soft">
                {q.prompt}
              </label>
              <input
                id={q.key}
                value={answers[q.key] ?? ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [q.key]: e.target.value }))}
                className="mt-2 min-h-[44px] w-full rounded-input border border-line bg-card px-3"
              />
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => void submitAnswers(true).then(() => navigate("/garden"))}
          className="mt-4 min-h-[44px] text-[13px] text-ink-soft underline"
        >
          先跳过，直接去种下
        </button>
      </section>

      <section className="mt-10">
        <h2 className="text-[20px]">种下一个愿望</h2>
        <textarea
          aria-label="写下一件还没发生的事"
          value={text}
          maxLength={500}
          rows={4}
          onChange={(e) => setText(e.target.value)}
          className="mt-3 w-full rounded-input border border-line bg-card p-3"
          placeholder="想去看海…"
        />
        <button
          type="button"
          disabled={busy || !text.trim()}
          onClick={() => void seed()}
          className="mt-3 min-h-[44px] rounded-[999px] bg-clay px-6 text-paper disabled:opacity-50"
        >
          {busy ? "正在收下…" : "种下它"}
        </button>
        {error && <p className="mt-3 rounded-card bg-card p-4 text-ink-soft">{error}</p>}
        {degraded && (
          <p className="mt-3 rounded-card bg-card p-4 text-ink-soft">
            我先把它原样存下来了，稍后再帮你读一遍。
          </p>
        )}
        {question && (
          <div className="mt-4 rounded-card border border-line bg-card p-4">
            <p>{question}</p>
            <button
              type="button"
              onClick={() => navigate("/garden")}
              className="mt-3 min-h-[44px] text-[13px] text-ink-soft underline"
            >
              以后再说
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
