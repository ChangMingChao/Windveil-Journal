/** 与 `logos/resources/api/*.yaml` 对齐的类型与 fetch 封装。
 *
 * access token 只放内存：refresh 由服务端下发 httpOnly Cookie，
 * 把 access token 写进 localStorage 等于把它交给任何一段能跑的脚本。
 */

export type WishState = "seeded" | "brewing" | "wind" | "going" | "happened" | "let_go";

export interface TimingOut {
  type: string | null;
  label: string;
  trigger_kind: "time" | "signal" | "none";
  next_trigger_at: string | null;
}

export interface WishCard {
  id: string;
  title: string;
  original_text_excerpt: string | null;
  seeded_at: string;
  state: WishState;
  let_go_at?: string | null;
  timing: TimingOut;
  soft_deferred: boolean;
  degraded_reason: string | null;
  version: number;
}

export interface WishDetail extends WishCard {
  original_text: string | null;
  understanding: Record<string, unknown> | null;
  pending_question: boolean;
  amended_from: string | null;
  current_step: Record<string, unknown> | null;
  timeline: { id: string; text: string; completed_at: string }[];
  messages: { id: string; role: string; text: string; created_at: string }[];
}

export interface WishListResponse {
  items: WishCard[];
  next_cursor: string | null;
}

export interface MemoryCard {
  id: string;
  wish_id: string;
  title: string;
  happened_from: string;
  happened_to: string | null;
  cover_media_id: string | null;
  status: "draft" | "published";
}

export interface Memory extends MemoryCard {
  cause: string | null;
  process: string | null;
  mood: string | null;
  last_line: string | null;
  photo_media_ids: string[];
  voice_media_id: string | null;
  note_before_seeded: boolean;
  edited_fields: ("title" | "cause" | "process")[];
  published_at: string | null;
  created_at: string;
}

export interface MemoryListResponse {
  items: MemoryCard[];
  next_cursor: string | null;
  lived_pages: number;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
