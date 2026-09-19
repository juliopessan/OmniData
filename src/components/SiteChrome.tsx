"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "./Logo";

export function SiteHeader() {
  const p = usePathname();
  const cur = (h: string) => (p === h ? "page" : undefined);
  return (
    <header className="site-head">
      <div className="wrap">
        <Link href="/" aria-label="OmniData — início"><Logo /></Link>
        <nav className="nav" aria-label="Principal">
          <Link href="/funcionalidades" aria-current={cur("/funcionalidades")}>Funcionalidades</Link>
          <Link href="/precos" aria-current={cur("/precos")}>Preços</Link>
          <Link href="/#seguranca">Segurança</Link>
        </nav>
        <div className="head-cta">
          <Link href="/login">Entrar</Link>
          <Link href="/cadastro" className="btn sm">Começar agora →</Link>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-foot">
      <div className="wrap cols">
        <div className="stack" style={{ maxWidth: 320 }}>
          <Link href="/"><Logo /></Link>
          <p>Inteligência de vendas no WhatsApp, alimentada pelo HubSpot. A primeira fatia de uma visão 360° do cliente.</p>
        </div>
        <div><span className="k">Produto</span><ul>
          <li><Link href="/funcionalidades">Funcionalidades</Link></li>
          <li><Link href="/precos">Preços</Link></li>
          <li><Link href="/dashboard">Demonstração</Link></li></ul></div>
        <div><span className="k">Conta</span><ul>
          <li><Link href="/login">Entrar</Link></li>
          <li><Link href="/cadastro">Criar conta</Link></li></ul></div>
        <div><span className="k">Legal</span><ul>
          <li>LGPD e consentimento</li><li>Retenção de dados</li></ul></div>
      </div>
    </footer>
  );
}
