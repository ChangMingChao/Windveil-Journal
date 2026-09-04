/** S08：时机建议与偏好的展示辅助。纯函数，无副作用。 */

/** 置信档文案：不展示裸百分比（IA 5.2 文案词典）。 */
export function tierOf(confidence: number): "比较确定" | "大概猜的" {
  return confidence >= 80 ? "比较确定" : "大概猜的";
}

/** 建议时机的卡面文案，复用 S03 的 6 选项措辞。 */
export function proposalLabel(
  timingType: TimingType,
  timingValue: string | null,
): string {
  switch (timingType) {
    case "season":
      return {
        spring: "入春",
        summer: "入夏",
        autumn: "入秋",
        winter: "入冬",
      }[timingValue as "spring" | "summer" | "autumn" | "winter"] ?? "某个季节到来";
    case "month_day":
      return timingValue ? `到 ${timingValue}` : "某个月份或纪念日";
    case "after_months":
      return timingValue === "1" ? "一个月后" : `${timingValue ?? "几"}个月后`;
    case "free_weekend":
      return "一个空闲的周末";
    case "month_day":
      return "某个月份或纪念日";
    case "after_months":
      return "多久之后再想想";
    case "free_weekend":
      return "当我有一个空闲周末时";
  }
}

type TimingType = "season" | "month_day" | "after_months" | "free_weekend";

export const PROPOSAL_COPY = {
  entry: "让 Agent 提个时候",
  thinking: "它在想了…",
  degraded: "它暂时没想出来，你可以先自己选一个",
  confirm: "就这样定",
  reject: "先不定",
  fallbackEntry: "还是我自己选一个时候",
  accepted: "你采纳了它的建议",
  because: "因为",
} as const;

/** 偏好来源徽标文案（IA 5.2：「我猜的」/「你说过的」）。 */
export function sourceLabel(source: "declared" | "inferred"): string {
  return source === "declared" ? "你说过的" : "我猜的";
}

export const REMEMBERED_COPY = {
  title: "它记得我什么",
  intro: "这里的东西只有你能看到，也随时可以让它忘掉。",
  inputPlaceholder: "用一句话告诉它，比如「更想和朋友一起」",
  record: "记下来",
  revoke: "猜错了",
  delete: "删掉",
  revokedSummary: "你看过的猜测",
  emptyTitle: "它还什么都不知道",
  emptyIntro: "你想让它记住什么？说一句就行。",
  availabilityTitle: "什么时候通常有空",
  availabilityAdd: "加一段",
} as const;

const WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"] as const;

export function weekdayName(weekday: number): string {
  return WEEKDAY_NAMES[weekday] ?? `周${weekday}`;
}

export function minuteLabel(minute: number): string {
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}
