import type { WishState } from "../api/types";

export const RECALL_COPY = {
  primary: "重新种下",
  secondary: "再放一会儿",
  success: "它已经回到刚种下的地方。",
} as const;

export function canRecall(state: WishState): boolean {
  return state === "let_go";
}
