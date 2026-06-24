"use client";
import { useEffect, useState } from "react";

export default function InfoBanner() {
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    setHidden(localStorage.getItem("flow_help_dismissed") === "1");
  }, []);

  if (hidden) return null;

  return (
    <div className="mb-4 rounded-lg border border-neutral-300 bg-neutral-50 p-4 text-sm">
      <div className="mb-1 font-semibold">How Flow works</div>
      <ol className="ml-4 list-decimal space-y-0.5 text-neutral-700">
        <li>
          An AI agent reads each transaction and proposes the accounting entry — but
          nothing is final yet. It is a draft.
        </li>
        <li>
          You review and Approve (or Reject) it here. Only on your approval does it post to
          the books.
        </li>
        <li>
          Every decision is written to a permanent audit log, and the consolidated P&amp;L
          updates instantly.
        </li>
      </ol>
      <button
        onClick={() => {
          localStorage.setItem("flow_help_dismissed", "1");
          setHidden(true);
        }}
        className="mt-2 text-xs text-neutral-600 underline hover:text-black"
      >
        Hide
      </button>
    </div>
  );
}
