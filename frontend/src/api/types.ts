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

export interface ProposalEvidence {
  kind: "preference" | "availability" | "timeline";
  id: string;
}

export interface TimingProposal {
  id: string;
  wish_id: string;
  status: "pending" | "confirmed" | "rejected" | "expired";
  timing_type: "season" | "month_day" | "after_months" | "free_weekend";
  timing_value: string | null;
  proposed_trigger_at: string | null;
  reason: string | null;
  confidence: number;
  evidence: ProposalEvidence[];
  validation: { valid: boolean; reason_code: string | null };
  created_at: string;
  expires_at: string;
  decided_at: string | null;
}

export interface WishDetail extends WishCard {
  original_text: string | null;
  understanding: Record<string, unknown> | null;
  pending_question: boolean;
  timing_proposal?: TimingProposal | null;
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

// ---------- auth.yaml（preferences tag，S08）----------

export interface PreferenceItem {
  id: string;
  kind: "entry" | "digest";
  pref_key: string;
  source: "declared" | "inferred";
  confidence: number;
  value: string;
  revoked_at: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface PreferenceListResponse {
  items: PreferenceItem[];
  digest: PreferenceItem | null;
}

export interface AvailabilityWindow {
  id: string;
  weekday: number;
  start_minute: number;
  end_minute: number;
  note: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface MeProfile {
  id: string;
  email: string | null;
  is_anonymous: boolean;
  onboarded_at: string | null;
  timezone: string;
  push_enabled: boolean;
  email_enabled: boolean;
  created_at: string;
}

export interface LiteEvent {
  id: string;
  text: string;
  status: "open" | "done";
  created_at: string;
  closed_at: string | null;
}
