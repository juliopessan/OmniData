"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  ["/dashboard", "Visão geral"], ["/dashboard/negocios", "Negócios"], ["/dashboard/alertas", "Alertas"],
  ["/dashboard/insights", "Insights"], ["/dashboard/reuniao", "Reunião de vendas"], ["/dashboard/equipe", "Equipe"], ["/dashboard/datasets", "Datasets"], ["/dashboard/whatsapp", "WhatsApp"], ["/dashboard/qualidade", "Qualidade dos dados"],
] as const;

export function DashNav() {
  const p = usePathname();
  return (
    <nav aria-label="Dashboard">
      {items.map(([h, l]) => <Link key={h} href={h} aria-current={p === h ? "page" : undefined}>{l}</Link>)}
    </nav>
  );
}
