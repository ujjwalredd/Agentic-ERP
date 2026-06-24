"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ProposedAction } from "@/lib/api";
import InfoBanner from "@/components/InfoBanner";

function LinesPreview({ payload }: { payload: any }) {
  if (payload?.lines) {
    return (
      <table className="mt-2 w-full text-xs text-neutral-600">
        <tbody>
          {payload.lines.map((l: any, i: number) => (
            <tr key={i} className="border-t border-neutral-100">
              <td className="py-1">account #{l.account_id}</td>
              <td className="py-1 text-right tabular-nums">
                {l.debit ? `Dr ${Number(l.debit).toFixed(2)}` : ""}
              </td>
              <td className="py-1 text-right tabular-nums">
                {l.credit ? `Cr ${Number(l.credit).toFixed(2)}` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  if (payload?.email) {
    return (
      <div className="mt-2 rounded border border-neutral-200 bg-neutral-50 p-2 text-xs text-neutral-700">
        <div className="font-semibold">{payload.email.subject}</div>
        <div className="mt-1 whitespace-pre-wrap">{payload.email.body}</div>
      </div>
    );
  }
  if (payload?.note) {
    return <div className="mt-2 text-xs italic text-neutral-600">{payload.note}</div>;
  }
  return null;
}

function EditPanel({
  action,
  onDone,
}: {
  action: ProposedAction;
  onDone: () => void;
}) {
  const [accounts, setAccounts] = useState<any[]>([]);
  const [accountCode, setAccountCode] = useState("");
  const [reason, setReason] = useState("");
  const [createRule, setCreateRule] = useState(false);
  const [autoApprove, setAutoApprove] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const eid = action.payload?.entity_id;
    if (eid)
      api.accounts(eid).then((a) =>
        setAccounts(a.filter((x: any) => ["expense", "revenue"].includes(x.type)))
      );
  }, [action]);

  async function save() {
    setBusy(true);
    try {
      await api.edit(action.id, {
        account_code: accountCode || undefined,
        reason,
        create_rule: createRule,
        auto_approve: autoApprove,
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 rounded-md border border-neutral-300 bg-neutral-50 p-3 text-sm">
      <div className="mb-2 font-medium">Correct this categorization</div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={accountCode}
          onChange={(e) => setAccountCode(e.target.value)}
          className="rounded border border-neutral-300 bg-white px-2 py-1 text-sm"
        >
          <option value="">Re-book to account…</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.code}>
              {a.code} {a.name}
            </option>
          ))}
        </select>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why? (teaches the system)"
          className="min-w-[220px] flex-1 rounded border border-neutral-300 bg-white px-2 py-1 text-sm"
        />
      </div>
      <label className="mt-2 flex items-center gap-2 text-xs text-neutral-700">
        <input
          type="checkbox"
          checked={createRule}
          onChange={(e) => setCreateRule(e.target.checked)}
        />
        Always do this — create a rule for this vendor
      </label>
      {createRule && (
        <label className="mt-1 flex items-center gap-2 text-xs text-neutral-700">
          <input
            type="checkbox"
            checked={autoApprove}
            onChange={(e) => setAutoApprove(e.target.checked)}
          />
          Auto-approve future matches (still audited &amp; reversible)
        </label>
      )}
      <div className="mt-3 flex gap-2">
        <button onClick={save} disabled={busy} className="btn">
          Approve as corrected
        </button>
        <button onClick={onDone} disabled={busy} className="btn-outline">
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function InboxPage() {
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [working, setWorking] = useState<number | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    try {
      setActions(await api.actions("pending"));
    } catch {
      /* worker may still be booting */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [load]);

  async function approve(id: number) {
    setWorking(id);
    try {
      await api.approve(id);
      await load();
    } finally {
      setWorking(null);
    }
  }

  async function doReject(id: number) {
    setWorking(id);
    try {
      await api.reject(id, reason);
      setRejecting(null);
      setReason("");
      await load();
    } finally {
      setWorking(null);
    }
  }

  return (
    <div>
      <InfoBanner />
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Approval Inbox</h1>
        <span className="text-sm text-neutral-500">{actions.length} pending</span>
      </div>

      {actions.length === 0 && (
        <div className="rounded-lg border border-dashed border-neutral-300 p-10 text-center text-neutral-500">
          No pending drafts. Fire a Simulate event above to wake the agents.
        </div>
      )}

      <div className="space-y-3">
        {actions.map((a) => (
          <div key={a.id} className="card p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="chip font-medium">{a.agent}</span>
                  <span className="text-xs text-neutral-500">{a.action_type}</span>
                  <span className="text-xs text-neutral-500">
                    confidence {(a.confidence * 100).toFixed(0)}%
                  </span>
                  {a.payload?.rule_id && <span className="chip">rule</span>}
                </div>
                <div className="mt-1 text-sm">{a.summary}</div>
                <LinesPreview payload={a.payload} />
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => approve(a.id)}
                  disabled={working === a.id}
                  className="btn"
                >
                  Approve
                </button>
                {a.action_type === "book_journal_entry" && (
                  <button
                    onClick={() => {
                      setEditing(editing === a.id ? null : a.id);
                      setRejecting(null);
                    }}
                    disabled={working === a.id}
                    className="btn-outline"
                  >
                    Edit
                  </button>
                )}
                <button
                  onClick={() => {
                    setRejecting(rejecting === a.id ? null : a.id);
                    setEditing(null);
                    setReason("");
                  }}
                  disabled={working === a.id}
                  className="btn-outline"
                >
                  Reject
                </button>
              </div>
            </div>

            {editing === a.id && (
              <EditPanel
                action={a}
                onDone={() => {
                  setEditing(null);
                  load();
                }}
              />
            )}

            {rejecting === a.id && (
              <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-neutral-300 bg-neutral-50 p-3">
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Reason for rejecting (optional, teaches the system)"
                  className="min-w-[260px] flex-1 rounded border border-neutral-300 bg-white px-2 py-1 text-sm"
                />
                <button onClick={() => doReject(a.id)} disabled={working === a.id} className="btn">
                  Confirm reject
                </button>
                <button onClick={() => setRejecting(null)} className="btn-outline">
                  Cancel
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
