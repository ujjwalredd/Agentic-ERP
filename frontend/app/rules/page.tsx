"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function RulesPage() {
  const [rules, setRules] = useState<any[]>([]);
  const [entities, setEntities] = useState<any[]>([]);
  const [pattern, setPattern] = useState("");
  const [accountCode, setAccountCode] = useState("");
  const [entityId, setEntityId] = useState<string>("");
  const [autoApprove, setAutoApprove] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [r, e] = await Promise.all([api.rules(), api.entities()]);
      setRules(r);
      setEntities(e);
    } catch {
      /* booting */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function add() {
    if (!pattern || !accountCode) return;
    setBusy(true);
    try {
      await api.createRule({
        pattern,
        account_code: accountCode,
        entity_id: entityId ? Number(entityId) : null,
        auto_approve: autoApprove,
      });
      setPattern("");
      setAccountCode("");
      setAutoApprove(false);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    await api.deleteRule(id);
    await load();
  }

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Rules</h1>
      <p className="mb-4 max-w-3xl text-sm text-neutral-500">
        Codified accounting knowledge. A rule maps a vendor pattern to a GL account
        deterministically — no AI guess. Auto-approve rules let matching transactions post
        without a click (still fully audited and reversible). Rules are also created
        automatically when you correct a draft with &quot;Always do this&quot;.
      </p>

      <div className="card mb-5 p-3">
        <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">New rule</div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            placeholder="Vendor contains… (e.g. AWS)"
            className="rounded border border-neutral-300 bg-white px-2 py-1 text-sm"
          />
          <input
            value={accountCode}
            onChange={(e) => setAccountCode(e.target.value)}
            placeholder="GL code (e.g. 5000)"
            className="w-40 rounded border border-neutral-300 bg-white px-2 py-1 text-sm"
          />
          <select
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            className="rounded border border-neutral-300 bg-white px-2 py-1 text-sm"
          >
            <option value="">All entities</option>
            {entities.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-xs text-neutral-700">
            <input
              type="checkbox"
              checked={autoApprove}
              onChange={(e) => setAutoApprove(e.target.checked)}
            />
            Auto-approve matches
          </label>
          <button onClick={add} disabled={busy} className="btn">
            Add rule
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-neutral-200">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left text-neutral-500">
            <tr>
              <th className="px-4 py-2 font-medium">Pattern</th>
              <th className="px-4 py-2 font-medium">Account</th>
              <th className="px-4 py-2 font-medium">Scope</th>
              <th className="px-4 py-2 font-medium">Auto</th>
              <th className="px-4 py-2 font-medium">Source</th>
              <th className="px-4 py-2 text-right font-medium">Hits</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.id} className="border-t border-neutral-100">
                <td className="px-4 py-2 font-medium">{r.pattern}</td>
                <td className="px-4 py-2">{r.account_code}</td>
                <td className="px-4 py-2 text-neutral-600">
                  {r.entity_id
                    ? entities.find((e) => e.id === r.entity_id)?.name || r.entity_id
                    : "All entities"}
                </td>
                <td className="px-4 py-2">{r.auto_approve ? <span className="chip">auto</span> : ""}</td>
                <td className="px-4 py-2 text-neutral-500">{r.source}</td>
                <td className="px-4 py-2 text-right tabular-nums">{r.hits}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => remove(r.id)} className="btn-outline">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {rules.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-4 text-neutral-500">
                  No rules yet. Add one above, or correct a draft with &quot;Always do this&quot;.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
