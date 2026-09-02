import type { ApiError } from "./types";

const BASE = "/api/v1";

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiError,
  ) {
    super(body.message || `HTTP ${status}`);
    this.name = "HttpError";
  }
}

export async function api<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, ...rest } = init;
  const headers = new Headers(rest.headers);
  if (json !== undefined) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const resp = await fetch(`${BASE}${path}`, {
    ...rest,
    headers,
    credentials: "include",
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });

  if (resp.status === 204) return undefined as T;
  const text = await resp.text();
  const parsed = text ? (JSON.parse(text) as unknown) : null;
  if (!resp.ok) {
    throw new HttpError(resp.status, (parsed as ApiError) ?? { code: "HTTP_ERROR", message: "" });
  }
  return parsed as T;
}
