import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader, SiteFooter } from "@/components/SiteChrome";
import { Eyebrow } from "@/components/Ledger";

export const metadata: Metadata = { title: "Preços" };

const plans = [
  { name: "Piloto", price: "R$ 0", per: "/ até 5 vendedores", cta: "Começar agora", items: ["Dados sintéticos ou HubSpot", "Assistente e alertas", "Suporte por e-mail"] },
  { name: "Time", price: "R$ 49", per: "/ vendedor / mês", cta: "Falar com vendas", items: ["Tudo do Piloto", "Motivo de perda e previsão", "Digest do gestor", "Backup noturno"] },
  { name: "Empresa", price: "Sob consulta", per: "", cta: "Falar com vendas", items: ["Tudo do Time", "SSO e trilha de auditoria", "Região São Paulo", "Novas fontes (suporte, cobrança)"] },
];

export default function Precos() {
  return (
    <>
      <SiteHeader />
      <main>
        <div className="wrap" style={{ padding: "72px 40px 48px" }}>
          <div className="stack" style={{ gap: 22 }}>
            <Eyebrow>Preços</Eyebrow>
            <h1 className="display" style={{ fontSize: "clamp(40px,6vw,72px)" }}>Simples como uma <span className="voice">planilha.</span></h1>
            <p className="lede">Valores ilustrativos para esta demonstração. Custos de canal (WhatsApp) e de LLM são exibidos por vendedor no painel.</p>
          </div>
        </div>
        <div className="wrap" style={{ paddingBottom: 72 }}>
          <div className="plans">
            {plans.map((p) => (
              <div className="plan" key={p.name}>
                <span className="tag" style={{ alignSelf: "flex-start" }}>{p.name}</span>
                <div className="price">{p.price} <small>{p.per}</small></div>
                <ul>{p.items.map((i) => <li key={i}>{i}</li>)}</ul>
                <Link href="/cadastro" className="btn">{p.cta}</Link>
              </div>
            ))}
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
