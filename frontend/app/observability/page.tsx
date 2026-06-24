"use client";
import { useCallback, useEffect, useState } from "react";
import { api, TRAINING_JSONL_URL } from "@/lib/api";

export default function ObservabilityPage() {
  const [stats, setStats] = useState<any>(null);
  const [traces, setTraces] = useState<any[]>([]);
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([api.obsStats(), api.traces(60)]);
      setStats(s);
      setTraces(t);
    } catch {
      /* booting */
    }
  }, []);

  useEffect(() => {
    load();
    const i = setInterval(load, 3000);
    return () => clearInterval(i);
  }, [load]);

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">
        AI Observability &amp; Learning Loop
      </h1>
      <p className="mb-4 max-w-3xl text-sm text-neutral-500">
        Every agent decision is logged with its full input, prompt, model, raw output, and
        latency. Each logged decision plus your approve/reject becomes a labeled training
        example — the corpus that makes the agents experts over time.
      </p>

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Decisions logged" value={stats?.total_traces ?? "..."} />
        <Stat label="Approved" value={stats?.human_decisions?.approved ?? 0} />
        <Stat label="Rejected" value={stats?.human_decisions?.rejected ?? 0} />
        <a href={TRAINING_JSONL_URL} className="card flex flex-col justify-center p-3 text-sm hover:bg-neutral-100">
          <span className="font-semibold">Export training data</span>
          <span className="text-xs text-neutral-500">labeled JSONL for fine-tuning</span>
        </a>
      </div>

      {stats?.agents?.length > 0 && (
        <div className="mb-5 overflow-hidden rounded-lg border border-neutral-200">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-left text-neutral-500">
              <tr>
                <th className="px-4 py-2 font-medium">Agent</th>
                <th className="px-4 py-2 text-right font-medium">Decisions</th>
                <th className="px-4 py-2 text-right font-medium">Avg confidence</th>
                <th className="px-4 py-2 text-right font-medium">Avg latency</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {stats.agents.map((a: any) => (
                <tr key={a.agent} className="border-t border-neutral-100">
                  <td className="px-4 py-2">{a.agent}</td>
                  <td className="px-4 py-2 text-right">{a.decisions}</td>
                  <td className="px-4 py-2 text-right">
                    {(a.avg_confidence * 100).toFixed(0)}%
                  </td>
                  <td className="px-4 py-2 text-right">{a.avg_latency_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="mb-2 text-xs uppercase tracking-wide text-neutral-500">Decision log</h2>
      <div className="space-y-2">
        {traces.map((t) => (
          <div key={t.id} className="card p-3">
            <button
              onClick={() => setOpen(open === t.id ? null : t.id)}
              className="flex w-full items-center justify-between text-left text-sm"
            >
              <span>
                <span className="font-medium">{t.agent}</span>{" "}
                <span className="text-neutral-500">{t.model}</span>
                {t.mock && <span className="chip ml-2">mock</span>}
              </span>
              <span className="text-xs tabular-nums text-neutral-500">
                {(t.confidence * 100).toFixed(0)}% · {t.latency_ms} ms
              </span>
            </button>
            {open === t.id && (
              <div className="mt-2 space-y-2 text-xs">
                <Field label="Input (prompt)" body={t.user_prompt} />
                <Field
                  label="Parsed decision"
                  body={JSON.stringify(t.parsed_decision, null, 2)}
                />
                <Field label="Raw model output" body={t.raw_response} />
              </div>
            )}
          </div>
        ))}
        {traces.length === 0 && (
          <div className="text-neutral-500">No agent decisions yet. Fire a Simulate event.</div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return (
    <div className="card p-3">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function Field({ label, body }: { label: string; body: string }) {
  return (
    <div>
      <div className="mb-1 text-neutral-500">{label}</div>
      <pre className="overflow-x-auto whitespace-pre-wrap rounded border border-neutral-200 bg-neutral-50 p-2 text-neutral-700">
        {body}
      </pre>
    </div>
  );
}
