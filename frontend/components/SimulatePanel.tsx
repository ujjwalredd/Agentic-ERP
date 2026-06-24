"use client";
import { useState } from "react";
import { api } from "@/lib/api";

const KINDS = [
  { kind: "bank_feed", label: "Bank feed", hint: "Categorizer" },
  { kind: "bill", label: "Vendor bill", hint: "Bill Handler" },
  { kind: "invoice", label: "Overdue AR", hint: "AR Clerk" },
  { kind: "intercompany", label: "Intercompany", hint: "Consolidator" },
  { kind: "close", label: "Month-end close", hint: "Closer / Reconciler / Reporter" },
];

export default function SimulatePanel() {
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  async function fire(kind: string) {
    setBusy(kind);
    setMsg("");
    try {
      const r = await api.simulate(kind);
      setMsg(`Fired ${r.count} event(s). Worker is routing — drafts appear in the Inbox.`);
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="border-b border-neutral-200 bg-neutral-50 px-6 py-3">
      <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">
        Simulate event
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {KINDS.map((k) => (
          <button
            key={k.kind}
            onClick={() => fire(k.kind)}
            disabled={!!busy}
            className="btn-outline"
            title={`Routes to ${k.hint}`}
          >
            {busy === k.kind ? "Working..." : k.label}
          </button>
        ))}
        {msg && <span className="ml-2 text-xs text-neutral-600">{msg}</span>}
      </div>
    </div>
  );
}
