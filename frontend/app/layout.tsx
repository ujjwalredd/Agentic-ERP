import "./globals.css";
import type { Metadata } from "next";
import Shell from "@/components/Shell";

export const metadata: Metadata = {
  title: "Flow — Agentic Accounting ERP",
  description: "AI agents do the accounting; humans approve.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
