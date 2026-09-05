import { useState } from "react";

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={`min-h-[44px] min-w-[44px] rounded-full border px-4 text-[13px] ${
        on ? "border-sprout bg-white text-sprout-deep" : "border-line bg-transparent text-ink-soft"
      }`}
    >
      {on ? "开" : "关"}
    </button>
  );
}
/** P6「我的」— S08「它记得我什么」区：偏好与可用时段的管理界面。

规格来源：core-05-preferences-availability-design.md。三条铁律：
  1. 来源徽标：「你说过的」（declared）强于「我猜的」（inferred）+ 置信档文案，不露裸百分比。
  2. 声明不覆盖推断：同主题的两条并列展示，可分别删除。
  3. 撤回（软失效，留痕迹）与删除（硬删，无影子）是两个动作；无任何条数统计。
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AvailabilityWindow, MeProfile, PreferenceItem } from "../api/types";
import {
  REMEMBERED_COPY,
  minuteLabel,
  sourceLabel,
  tierOf,
  weekdayName,
} from "../lib/remembered";

const PREF_KEYS = [
  { key: "relaxation", label: "放松" },
  { key: "pace", label: "节奏" },
  { key: "companion", label: "同行" },
  { key: "budget", label: "预算" },
  { key: "other", label: "其他" },
] as const;

const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"] as const;

export default function Me() {
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [prefKey, setPrefKey] = useState<string>("companion");
  const [weekday, setWeekday] = useState(5);
  const [start, setStart] = useState(540);
  const [end, setEnd] = useState(720);
  const [showRevoked, setShowRevoked] = useState(false);
  const [showAvailabilityForm, setShowAvailabilityForm] = useState(false);

  const prefs = useQuery({
    queryKey: ["preferences", showRevoked],
    queryFn: () =>
      api<{ items: PreferenceItem[]; digest: PreferenceItem | null }>(
        `/me/preferences${showRevoked ? "?include_revoked=true" : ""}`,
      ),
  });

  const channelsQ = useQuery({
    queryKey: ["channels"],
    queryFn: () => api<MeProfile>("/me"),
  });

  const saveChannels = useMutation({
    mutationFn: async (changes: { push_enabled?: boolean; email_enabled?: boolean }) =>
      api<{ push_enabled: boolean; email_enabled: boolean }>("/me/notification-channels", {
        method: "PATCH",
        json: changes,
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["channels"] }),
  });

  const availability = useQuery({
    queryKey: ["availability"],
    queryFn: () => api<{ items: AvailabilityWindow[] }>("/me/availability"),
  });

  const declare = useMutation({
    mutationFn: async () => api(`/me/preferences`, { method: "PUT", json: { pref_key: prefKey, value: text } }),
    onSuccess: () => {
      setText("");
      void client.invalidateQueries({ queryKey: ["preferences"] });
    },
  });

  const revoke = useMutation({
    mutationFn: async (id: string) => api(`/me/preferences/${id}/revoke`, { method: "POST" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["preferences"] }),
  });

  const removePref = useMutation({
    mutationFn: async (id: string) => api(`/me/preferences/${id}`, { method: "DELETE" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["preferences"] }),
  });

  const addWindow = useMutation({
    mutationFn: async () =>
      api(`/me/availability`, {
        method: "POST",
        json: { weekday, start_minute: start, end_minute: end },
      }),
    onSuccess: () => {
      setShowAvailabilityForm(false);
      void client.invalidateQueries({ queryKey: ["availability"] });
    },
  });

  const removeWindow = useMutation({
    mutationFn: async (id: string) => api(`/me/availability/${id}`, { method: "DELETE" }),
    onSuccess: () => void client.invalidateQueries({ queryKey: ["availability"] }),
  });

  const items = prefs.data?.items ?? [];
  const entries = items.filter((i) => i.kind === "entry" && i.revoked_at === null);
  const revoked = items.filter((i) => i.kind === "entry" && i.revoked_at !== null);
  const windows = availability.data?.items ?? [];
  const channels = {
    push_enabled: channelsQ.data?.push_enabled ?? true,
    email_enabled: channelsQ.data?.email_enabled ?? true,
  };
  const invalidRange = end <= start;

  return (
    <main className="mx-auto max-w-[560px] px-4 pb-24">
      <h1 className="mt-6 text-[28px]">{REMEMBERED_COPY.title}</h1>
      <p className="mt-2 text-[13px] text-ink-soft">{REMEMBERED_COPY.intro}</p>

      {entries.length === 0 ? (
        <section className="mt-10 text-center">
          <h2 className="text-[20px]">{REMEMBERED_COPY.emptyTitle}</h2>
          <p className="mt-2 text-[13px] text-ink-soft">{REMEMBERED_COPY.emptyIntro}</p>
        </section>
      ) : (
        <ul className="mt-6 flex flex-col gap-3">
          {entries.map((item) => (
            <li key={item.id} className="rounded-card border border-line bg-card p-4 shadow-lamp">
              <div className="flex items-center justify-between gap-2">
                <span
                  className={
                    item.source === "declared"
                      ? "text-[13px] font-medium text-sprout-deep"
                      : "text-[13px] text-mist-deep"
                  }
                >
                  {sourceLabel(item.source)}
                </span>
                {item.source === "inferred" && (
                  <span className="rounded-full border border-line px-2 py-0.5 text-[12px] text-mist-deep">
                    {tierOf(item.confidence)}
                  </span>
                )}
              </div>
              <p className="mt-1">{item.value}</p>
              <div className="mt-2 flex gap-3">
                {item.source === "inferred" && (
                  <button
                    type="button"
                    onClick={() => revoke.mutate(item.id)}
                    disabled={revoke.isPending}
                    className="min-h-[44px] text-[13px] text-clay underline underline-offset-4"
                  >
                    {REMEMBERED_COPY.revoke}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => removePref.mutate(item.id)}
                  disabled={removePref.isPending}
                  className="min-h-[44px] text-[13px] text-ink-soft underline underline-offset-4"
                >
                  {REMEMBERED_COPY.delete}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <details className="mt-4" onToggle={(e) => setShowRevoked((e.target as HTMLDetailsElement).open)}>
        <summary className="cursor-pointer text-[13px] text-ink-soft">
          {REMEMBERED_COPY.revokedSummary}
        </summary>
        <ul className="mt-2 flex flex-col gap-2">
          {revoked.map((item) => (
            <li key={item.id} className="text-[13px] text-ink-soft">
              你撤回了它（{item.value}）
            </li>
          ))}
        </ul>
      </details>

      <section className="mt-8 rounded-card border border-line bg-card p-4">
        <label className="text-[14px]" htmlFor="declare-input">
          想让它记住什么？
        </label>
        <div className="mt-2 flex flex-wrap gap-2">
          {PREF_KEYS.map((k) => (
            <button
              key={k.key}
              type="button"
              onClick={() => setPrefKey(k.key)}
              className={`min-h-[36px] rounded-full border px-3 text-[13px] ${
                prefKey === k.key ? "border-clay bg-white text-clay" : "border-line text-ink-soft"
              }`}
            >
              {k.label}
            </button>
          ))}
        </div>
        <input
          id="declare-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={200}
          placeholder={REMEMBERED_COPY.inputPlaceholder}
          className="mt-2 min-h-[48px] w-full rounded-[14px] border border-line bg-white px-4"
        />
        <button
          type="button"
          onClick={() => declare.mutate()}
          disabled={text.trim().length === 0 || declare.isPending}
          className="mt-3 min-h-[44px] rounded-[999px] bg-clay px-5 text-paper disabled:opacity-50"
        >
          {REMEMBERED_COPY.record}
        </button>
      </section>

      <hr className="my-8 border-dashed border-line" />

      <section>
        <h2 className="text-[20px]">提醒通道</h2>
        <p className="mt-1 text-[13px] text-ink-soft">安静是你的选择，随时可以打开。</p>
        <div className="mt-3 flex flex-col gap-2">
          <div className="flex items-center justify-between rounded-card border border-line bg-card px-4 py-3">
            <span className="text-[14px]">浏览器推送</span>
            <Toggle
              on={channels.push_enabled}
              onChange={(v) => saveChannels.mutate({ push_enabled: v })}
            />
          </div>
          <div className="flex items-center justify-between rounded-card border border-line bg-card px-4 py-3">
            <span className="text-[14px]">邮件兜底（iOS 建议保持开启）</span>
            <Toggle
              on={channels.email_enabled}
              onChange={(v) => saveChannels.mutate({ email_enabled: v })}
            />
          </div>
          {!channels.push_enabled && !channels.email_enabled && (
            <p className="text-[13px] text-ink-soft">先安静一段时间，想听的时候随时打开。</p>
          )}
        </div>
      </section>

      <hr className="my-8 border-dashed border-line" />

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-[20px]">{REMEMBERED_COPY.availabilityTitle}</h2>
          <button
            type="button"
            onClick={() => setShowAvailabilityForm((v) => !v)}
            className="min-h-[44px] text-[13px] text-clay underline underline-offset-4"
          >
            {REMEMBERED_COPY.availabilityAdd}
          </button>
        </div>
        <ul className="mt-3 flex flex-col gap-2">
          {windows.map((w) => (
            <li key={w.id} className="flex items-center justify-between rounded-card border border-line bg-card px-4 py-3">
              <span className="text-[14px]">
                {weekdayName(w.weekday)} {minuteLabel(w.start_minute)}–{minuteLabel(w.end_minute)}
              </span>
              <button
                type="button"
                onClick={() => removeWindow.mutate(w.id)}
                className="min-h-[44px] text-[13px] text-ink-soft underline underline-offset-4"
              >
                {REMEMBERED_COPY.delete}
              </button>
            </li>
          ))}
        </ul>

        {showAvailabilityForm && (
          <div className="mt-3 rounded-card border border-line bg-card p-4">
            <div className="flex flex-wrap gap-2">
              {WEEKDAYS.map((name, i) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => setWeekday(i)}
                  className={`min-h-[36px] rounded-full border px-3 text-[13px] ${
                    weekday === i ? "border-clay bg-white text-clay" : "border-line text-ink-soft"
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-3 text-[14px]">
              <label htmlFor="avail-start">从</label>
              <input
                id="avail-start"
                type="time"
                value={minuteLabel(start)}
                step={600}
                onChange={(e) => setStart(Number(e.target.value.slice(0, 2)) * 60 + Number(e.target.value.slice(3, 5)))}
                className="rounded-[14px] border border-line bg-white px-3 py-2"
              />
              <label htmlFor="avail-end">到</label>
              <input
                id="avail-end"
                type="time"
                value={minuteLabel(end)}
                onChange={(e) => setEnd(Number(e.target.value.slice(0, 2)) * 60 + Number(e.target.value.slice(3, 5)))}
                className="rounded-[14px] border border-line bg-white px-3 py-2"
              />
            </div>
            {invalidRange && <p className="mt-2 text-[13px] text-clay">结束要晚于开始</p>}
            <button
              type="button"
              onClick={() => addWindow.mutate()}
              disabled={invalidRange || addWindow.isPending}
              className="mt-3 min-h-[44px] rounded-[999px] border border-line px-5 text-clay disabled:opacity-50"
            >
              {REMEMBERED_COPY.record}
            </button>
          </div>
        )}
      </section>
    </main>
  );
}