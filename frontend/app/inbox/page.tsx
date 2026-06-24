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

export default function InboxPage() {
  const [actions, setActions] = useState<ProposedAction[]>([]);
  const [working, setWorking] = useState<number | null>(null);

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

  async function act(id: number, kind: "approve" | "reject") {
    setWorking(id);
    try {
      await (kind === "approve" ? api.approve(id) : api.reject(id));
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
                </div>
                <div className="mt-1 text-sm">{a.summary}</div>
                <LinesPreview payload={a.payload} />
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => act(a.id, "approve")}
                  disabled={working === a.id}
                  className="btn"
                >
                  Approve
                </button>
                <button
                  onClick={() => act(a.id, "reject")}
                  disabled={working === a.id}
                  className="btn-outline"
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
