import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader, SiteFooter } from "@/components/SiteChrome";
import { Eyebrow } from "@/components/Ledger";
import { FeatureList } from "@/components/FeatureList";

export const metadata: Metadata = { title: "Funcionalidades" };

export default function Funcionalidades() {
  return (
    <>
      <SiteHeader />
      <main>
        <div className="wrap" style={{ padding: "72px 40px 40px" }}>
          <div className="stack" style={{ gap: 22 }}>
            <Eyebrow>Funcionalidades</Eyebrow>
            <h1 className="display" style={{ fontSize: "clamp(40px,6vw,72px)" }}>Tudo o que o time comercial <span className="voice">precisa saber.</span></h1>
            <p className="lede">Organizado por tema. Cada funcionalidade tem uma manchete, uma explicação curta e um exemplo de conversa real no WhatsApp.</p>
          </div>
        </div>
        <div className="wrap"><FeatureList /></div>
        <section className="section">
          <div className="wrap stack" style={{ alignItems: "flex-start" }}>
            <h2 className="h2">Pronto para ver no seu pipeline?</h2>
            <Link href="/cadastro" className="btn">Começar agora →</Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
