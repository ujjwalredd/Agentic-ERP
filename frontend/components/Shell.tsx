"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import SimulatePanel from "@/components/SimulatePanel";
import AuthGate from "@/components/AuthGate";
import { api } from "@/lib/api";

function UserBar() {
  const router = useRouter();
  const [who, setWho] = useState<{ email: string; role: string } | null>(null);
  useEffect(() => {
    api.me().then(setWho).catch(() => setWho(null));
  }, []);
  return (
    <div className="flex items-center justify-end gap-3 border-b border-neutral-200 px-6 py-2 text-xs text-neutral-600">
      {who && (
        <span>
          {who.email} <span className="text-neutral-400">({who.role})</span>
        </span>
      )}
      <button
        className="rounded-md border border-neutral-300 px-2 py-1 hover:bg-neutral-100"
        onClick={() => {
          api.logout();
          router.replace("/login");
        }}
      >
        Sign out
      </button>
    </div>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();

  // The login screen renders full-bleed, without the app chrome.
  if (path === "/login") return <>{children}</>;

  return (
    <AuthGate>
      <div className="flex min-h-screen">
        <Nav />
        <main className="flex-1">
          <UserBar />
          <SimulatePanel />
          <div className="p-6">{children}</div>
        </main>
      </div>
    </AuthGate>
  );
}
