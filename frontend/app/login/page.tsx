"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("controller@demo");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api.login(email, password);
      router.push("/inbox");
    } catch (e: any) {
      setErr(e.message || "login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-50">
      <form
        onSubmit={submit}
        className="w-80 space-y-4 rounded-lg border border-neutral-200 bg-white p-6 shadow-sm"
      >
        <div>
          <div className="text-lg font-bold tracking-tight">Agentic Accounting ERP</div>
          <div className="text-xs text-neutral-500">Sign in to continue</div>
        </div>
        <label className="block text-sm">
          <span className="text-neutral-600">Email</span>
          <input
            className="mt-1 w-full rounded-md border border-neutral-300 px-3 py-2 text-sm"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
          />
        </label>
        <label className="block text-sm">
          <span className="text-neutral-600">Password</span>
          <input
            type="password"
            className="mt-1 w-full rounded-md border border-neutral-300 px-3 py-2 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {err && <div className="text-xs text-red-600">{err}</div>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-black px-3 py-2 text-sm text-white disabled:opacity-50"
        >
          {busy ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
