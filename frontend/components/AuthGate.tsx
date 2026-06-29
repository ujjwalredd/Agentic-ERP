"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";

/**
 * Resolves the current principal via GET /auth/me.
 * - Open-dev / shared-token backends return a principal with no token, so the app
 *   just renders (no login required).
 * - JWT-mode backends return 401 without a valid token, so we redirect to /login.
 * Exposes the resolved user/role to the layout chrome.
 */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [state, setState] = useState<"loading" | "ok" | "anon">("loading");

  useEffect(() => {
    if (path === "/login") {
      setState("ok");
      return;
    }
    api
      .me()
      .then(() => setState("ok"))
      .catch((e) => {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
          setState("anon");
          router.replace("/login");
        } else {
          // Network/other error: don't lock the user out of a local dev backend.
          setState("ok");
        }
      });
  }, [path, router]);

  if (state === "loading")
    return <div className="p-6 text-sm text-neutral-500">Loading…</div>;
  if (state === "anon") return null;
  return <>{children}</>;
}
