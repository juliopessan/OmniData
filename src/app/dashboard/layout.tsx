import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { DashNav } from "@/components/DashNav";

export const metadata: Metadata = { title: { default: "Dashboard", template: "%s · Dashboard · OmniData" } };

export default function DashLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <aside className="side">
        <Link href="/" aria-label="OmniData — início"><Logo /></Link>
        <DashNav />
        <div className="who">
          <b style={{ color: "var(--ink)" }}>Gestor Demo</b><br />
          <Link href="/login" style={{ textDecoration: "underline" }}>Sair</Link>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
