const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || "";

async function req(path: string, init?: RequestInit) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (TOKEN) headers["Authorization"] = `Bearer ${TOKEN}`;
  const res = await fetch(`${BASE}${path}`, {
    headers,
    cache: "no-store",
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
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
  actions: (status = "pending"): Promise<ProposedAction[]> =>
    req(`/inbox/actions?status=${status}`),
  approve: (id: number) =>
    req(`/inbox/actions/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ user_id: "demo-user" }),
    }),
  reject: (id: number) =>
    req(`/inbox/actions/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ user_id: "demo-user" }),
    }),
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
};

export const TRAINING_JSONL_URL = `${BASE}/observability/training-data.jsonl`;
