const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "flow_token";

// Per-user JWT, minted by POST /auth/login and kept in localStorage. (No more
// build-time NEXT_PUBLIC_API_TOKEN baked into the browser bundle.)
export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(TOKEN_KEY) || "";
}
export function setToken(token: string) {
  if (typeof window !== "undefined") window.localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req(path: string, init?: RequestInit) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}${path}`, {
    headers,
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw new ApiError(res.status, `${res.status} ${await res.text()}`);
  }
  return res.json();
}

export type ProposedAction = {
  id: number;
  agent: string;
  action_type: string;
  summary: string;
  confidence: number;
  payload: any;
  status: string;
  created_at: string;
};

export type AuditLog = {
  id: number;
  timestamp: string;
  user_id: string;
  agent: string;
  action: string;
  proposed_action_id: number;
  before: any;
  after: any;
};

export const api = {
  login: async (email: string, password: string) => {
    const r = await req(`/auth/login`, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(r.access_token);
    return r as { email: string; role: string; access_token: string };
  },
  me: (): Promise<{ email: string; role: string }> => req(`/auth/me`),
  logout: () => clearToken(),
  actions: (status = "pending"): Promise<ProposedAction[]> =>
    req(`/inbox/actions?status=${status}`),
  approve: (id: number) =>
    req(`/inbox/actions/${id}/approve`, { method: "POST" }),
  reject: (id: number, reason = "") =>
    req(`/inbox/actions/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  edit: (
    id: number,
    body: { account_code?: string; reason?: string; create_rule?: boolean; auto_approve?: boolean }
  ) =>
    req(`/inbox/actions/${id}/edit`, { method: "POST", body: JSON.stringify(body) }),
  audit: (): Promise<AuditLog[]> => req(`/inbox/audit`),
  entries: (entityId?: number, status?: string) => {
    const q = new URLSearchParams();
    if (entityId) q.set("entity_id", String(entityId));
    if (status) q.set("status", status);
    return req(`/ledger/entries?${q.toString()}`);
  },
  accounts: (entityId?: number) =>
    req(`/ledger/accounts${entityId ? `?entity_id=${entityId}` : ""}`),
  bank: (entityId?: number) =>
    req(`/ledger/bank${entityId ? `?entity_id=${entityId}` : ""}`),
  entities: () => req(`/entities`),
  consolidatedPnl: () => req(`/reports/consolidated-pnl`),
  simulate: (kind: string) =>
    req(`/simulate`, { method: "POST", body: JSON.stringify({ kind }) }),
  traces: (limit = 100) => req(`/observability/traces?limit=${limit}`),
  obsStats: () => req(`/observability/stats`),
  trainingData: () => req(`/observability/training-data?labeled_only=true`),
  rules: () => req(`/rules`),
  createRule: (body: {
    entity_id?: number | null;
    match_type?: string;
    pattern: string;
    account_code: string;
    auto_approve?: boolean;
    min_confidence?: number;
  }) => req(`/rules`, { method: "POST", body: JSON.stringify(body) }),
  deleteRule: (id: number) => req(`/rules/${id}`, { method: "DELETE" }),
};

export const TRAINING_JSONL_URL = `${BASE}/observability/training-data.jsonl`;
