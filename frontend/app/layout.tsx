import "./globals.css";
import type { Metadata } from "next";
import Nav from "@/components/Nav";
import SimulatePanel from "@/components/SimulatePanel";

export const metadata: Metadata = {
  title: "Flow — Agentic Accounting ERP",
  description: "AI agents do the accounting; humans approve.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="flex min-h-screen">
          <Nav />
          <main className="flex-1">
            <SimulatePanel />
            <div className="p-6">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
