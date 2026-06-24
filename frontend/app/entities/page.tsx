"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function EntitiesPage() {
  const [entities, setEntities] = useState<any[]>([]);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [sel, setSel] = useState<number | null>(null);

  useEffect(() => {
    api.entities().then((e) => {
      setEntities(e);
      if (e.length) setSel(e[0].id);
    });
  }, []);

  useEffect(() => {
    if (sel) api.accounts(sel).then(setAccounts);
  }, [sel]);

  return (
    <div>
      <h1 className="mb-3 text-xl font-semibold tracking-tight">
        Entities &amp; Chart of Accounts
      </h1>
      <div className="grid grid-cols-[220px_1fr] gap-6">
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-neutral-500">
            Entity tree
          </div>
          <ul className="space-y-1">
            {entities.map((e) => (
              <li key={e.id} style={{ marginLeft: e.parent_id ? 16 : 0 }}>
                <button
                  onClick={() => setSel(e.id)}
                  className={`w-full rounded-md px-3 py-1.5 text-left text-sm transition-colors ${
                    sel === e.id ? "bg-black text-white" : "hover:bg-neutral-100"
                  }`}
                >
                  {e.parent_id ? "— " : ""}
                  {e.name}{" "}
                  <span className={sel === e.id ? "text-neutral-300" : "text-neutral-400"}>
                    {e.currency}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="overflow-hidden rounded-lg border border-neutral-200">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-left text-neutral-500">
              <tr>
                <th className="px-4 py-2 font-medium">Code</th>
                <th className="px-4 py-2 font-medium">Account</th>
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Intercompany</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((a) => (
                <tr key={a.id} className="border-t border-neutral-100">
                  <td className="px-4 py-2 text-neutral-500">{a.code}</td>
                  <td className="px-4 py-2">{a.name}</td>
                  <td className="px-4 py-2 capitalize text-neutral-600">{a.type}</td>
                  <td className="px-4 py-2">
                    {a.is_intercompany ? <span className="chip">eliminated</span> : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
