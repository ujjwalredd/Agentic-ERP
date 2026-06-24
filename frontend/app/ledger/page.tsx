"use client";
import { useCallback, useEffect, useState } from "react";
import { api, AuditLog } from "@/lib/api";

type Tab = "entries" | "audit";

function money(n: number) {
  return n ? n.toLocaleString("en-US", { minimumFractionDigits: 2 }) : "";
}

export default function LedgerPage() {
  const [tab, setTab] = useState<Tab>("entries");
  const [entries, setEntries] = useState<any[]>([]);
  const [audit, setAudit] = useState<AuditLog[]>([]);

  const load = useCallback(async () => {
    try {
      const [e, a] = await Promise.all([api.entries(), api.audit()]);
      setEntries(e);
      setAudit(a);
    } catch {
      /* booting */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div>
      <h1 className="mb-3 text-xl font-semibold tracking-tight">Ledger &amp; Audit Trail</h1>
      <div className="mb-4 flex gap-2">
        {(["entries", "audit"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={tab === t ? "btn" : "btn-outline"}
          >
            {t === "entries" ? "Journal Entries" : "Audit Log (immutable)"}
          </button>
        ))}
      </div>

      {tab === "entries" && (
        <div className="space-y-2">
          {entries.map((e) => (
            <div key={e.id} className="card p-3">
              <div className="flex items-center justify-between text-sm">
                <div>
                  <span className="text-neutral-400">#{e.id}</span> {e.memo}
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-neutral-500">entity {e.entity_id}</span>
                  <span className="text-neutral-500">{e.created_by_agent}</span>
                  <span
                    className={
                      e.status === "posted"
                        ? "rounded bg-black px-2 py-0.5 text-white"
                        : "rounded border border-neutral-300 px-2 py-0.5 text-neutral-600"
                    }
                  >
                    {e.status}
                  </span>
                </div>
              </div>
              <table className="mt-2 w-full text-xs text-neutral-600">
                <tbody className="tabular-nums">
                  {e.lines.map((l: any, i: number) => (
                    <tr key={i} className="border-t border-neutral-100">
                      <td className="py-1">
                        {l.account_code} {l.account_name}
                      </td>
                      <td className="py-1 text-right">{money(l.debit)}</td>
                      <td className="py-1 text-right">{money(l.credit)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {entries.length === 0 && (
            <div className="text-neutral-500">No journal entries yet.</div>
          )}
        </div>
      )}

      {tab === "audit" && (
        <div className="overflow-hidden rounded-lg border border-neutral-200">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-left text-neutral-500">
              <tr>
                <th className="px-4 py-2 font-medium">When</th>
                <th className="px-4 py-2 font-medium">User</th>
                <th className="px-4 py-2 font-medium">Agent</th>
                <th className="px-4 py-2 font-medium">Action</th>
                <th className="px-4 py-2 font-medium">Result</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id} className="border-t border-neutral-100">
                  <td className="px-4 py-2 text-neutral-500">
                    {new Date(a.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-2">{a.user_id}</td>
                  <td className="px-4 py-2">{a.agent}</td>
                  <td className="px-4 py-2 font-medium">{a.action}</td>
                  <td className="px-4 py-2 text-xs text-neutral-500">
                    {JSON.stringify(a.after)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {audit.length === 0 && (
            <div className="p-4 text-neutral-500">No decisions recorded yet.</div>
          )}
        </div>
      )}
    </div>
  );
}
