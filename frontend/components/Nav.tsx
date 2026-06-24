"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/inbox", label: "Approval Inbox" },
  { href: "/reports", label: "Consolidated P&L" },
  { href: "/ledger", label: "Ledger & Audit" },
  { href: "/observability", label: "AI Observability" },
  { href: "/entities", label: "Entities & CoA" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="w-56 shrink-0 border-r border-neutral-200 p-4">
      <div className="mb-6">
        <div className="text-lg font-bold tracking-tight">Flow</div>
        <div className="text-xs text-neutral-500">Agentic Accounting ERP</div>
      </div>
      <ul className="space-y-1">
        {links.map((l) => {
          const active = path?.startsWith(l.href);
          return (
            <li key={l.href}>
              <Link
                href={l.href}
                className={`block rounded-md px-3 py-2 text-sm transition-colors ${
                  active
                    ? "bg-black text-white"
                    : "text-neutral-700 hover:bg-neutral-100"
                }`}
              >
                {l.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
