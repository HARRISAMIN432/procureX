import type { Session } from "../types";

export const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string, public requestId?: string) { super(message); }
}

export async function api<T>(session: Session, path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Organization-ID", session.organizationId);
  headers.set("X-Request-ID", crypto.randomUUID());
  if (options.body) headers.set("Content-Type", "application/json");
  if (session.mode === "oidc" && session.accessToken) headers.set("Authorization", `Bearer ${session.accessToken}`);
  if (session.mode === "dev" && session.userId) headers.set("X-User-ID", session.userId);
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string | { message?: string } };
    const message = typeof payload.detail === "string" ? payload.detail : payload.detail?.message || "The request could not be completed.";
    throw new ApiError(response.status, message, response.headers.get("X-Request-ID") || undefined);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const post = <T>(session: Session, path: string, body: unknown) => api<T>(session, path, { method: "POST", body: JSON.stringify(body) });
export const patch = <T>(session: Session, path: string, body: unknown) => api<T>(session, path, { method: "PATCH", body: JSON.stringify(body) });
