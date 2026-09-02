/** 河流视图的排序：按 next_trigger_at 升序，没有时机的排最后。
 *
 * 这是**纯前端重排**（S05.1 Step 14）：两个视图用的是同一批字段，
 * 多打一次接口只会让切换出现可感知的等待。也正因如此，
 * 「切换视图不丢失筛选」是结构上的必然，而不是需要额外保证的行为。
 *
 * 覆盖用例：UT-S05-19（排序键与 null 的位置）、UT-S05-20 与 ST-S05-02
 * （切换视图不触发新请求）。
 */
import type { WishCard } from "../api/types";

export type GardenView = "garden" | "river";

/** 接受 WishCard，也接受只带 next_trigger_at 的裸对象——UT 里两种都会用到。 */
type Sortable = WishCard | { next_trigger_at: string | null };

export function sortForRiver<T extends Sortable>(items: readonly T[]): T[] {
  return [...items].sort((a, b) => {
    const left = triggerOf(a);
    const right = triggerOf(b);
    if (left === null && right === null) return 0;
    if (left === null) return 1; // null 一律排最后
    if (right === null) return -1;
    return left - right;
  });
}

function triggerOf(item: unknown): number | null {
  const raw =
    typeof item === "object" && item !== null
      ? ((item as WishCard).timing?.next_trigger_at ??
        (item as { next_trigger_at?: string | null }).next_trigger_at ??
        null)
      : null;
  if (!raw) return null;
  const parsed = Date.parse(raw);
  return Number.isNaN(parsed) ? null : parsed;
}

/** 花园视图保持接口返回的顺序（seeded_at 倒序，由服务端决定）。 */
export function orderFor<T extends WishCard>(items: readonly T[], view: GardenView): T[] {
  return view === "river" ? sortForRiver(items) : [...items];
}
