"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

function money(n: number) {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export default function ReportsPage() {
  const [pnl, setPnl] = useState<any>(null);

  const load = useCallback(async () => {
    try {
      setPnl(await api.consolidatedPnl());
    } catch {
      /* booting */
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  if (!pnl) return <div className="text-neutral-500">Loading...</div>;

  const c = pnl.consolidated;
  const e = pnl.eliminations;

  return (
    <div>
      <div className="mb-1 flex items-center gap-2">
        <h1 className="text-xl font-semibold tracking-tight">Consolidated P&amp;L</h1>
        <span className="chip">live — updates as drafts are approved</span>
      </div>
      <p className="mb-4 max-w-3xl text-sm text-neutral-500">
        Each subsidiary&apos;s posted results, the intercompany eliminations, and the
        consolidated group total. Eliminations zero out internal revenue/expense so the
        group is not double-counting itself.
      </p>

      <div className="overflow-hidden rounded-lg border border-neutral-200">
        <table className="w-full text-sm">
          <thead className="bg-neutral-50 text-left text-neutral-500">
            <tr>
              <th className="px-4 py-2 font-medium">Entity</th>
              <th className="px-4 py-2 text-right font-medium">Revenue</th>
              <th className="px-4 py-2 text-right font-medium">Expense</th>
              <th className="px-4 py-2 text-right font-medium">Net income</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {pnl.entities.map((row: any) => (
              <tr key={row.entity_id} className="border-t border-neutral-100">
                <td className="px-4 py-2">{row.entity}</td>
                <td className="px-4 py-2 text-right">{money(row.revenue)}</td>
                <td className="px-4 py-2 text-right">{money(row.expense)}</td>
                <td className="px-4 py-2 text-right">{money(row.net_income)}</td>
              </tr>
            ))}
            <tr className="border-t border-neutral-200 text-neutral-500">
              <td className="px-4 py-2 italic">Intercompany eliminations</td>
              <td className="px-4 py-2 text-right">{money(e.revenue)}</td>
              <td className="px-4 py-2 text-right">{money(e.expense)}</td>
              <td className="px-4 py-2 text-right">{money(e.net_income)}</td>
            </tr>
            <tr className="border-t-2 border-black bg-neutral-50 font-semibold">
              <td className="px-4 py-2">Consolidated group</td>
              <td className="px-4 py-2 text-right">{money(c.revenue)}</td>
              <td className="px-4 py-2 text-right">{money(c.expense)}</td>
              <td className="px-4 py-2 text-right">{money(c.net_income)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {e.rows?.length > 0 && (
        <div className="mt-4 text-xs text-neutral-500">
          Eliminated lines:{" "}
          {e.rows.map((r: any, i: number) => (
            <span key={i} className="mr-3">
              {r.name} ({money(r.amount)})
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
