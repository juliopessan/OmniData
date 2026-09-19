import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { AuthForm } from "@/components/AuthForm";
import { Eyebrow } from "@/components/Ledger";

export const metadata: Metadata = { title: "Criar conta" };

export default function Cadastro() {
  return (
    <div className="auth">
      <aside className="auth-side">
        <Link href="/" style={{ color: "var(--ledger-ink)" }}><Logo /></Link>
        <div className="stack" style={{ gap: 18 }}>
          <Eyebrow>Em três etapas</Eyebrow>
          <h1 className="h2">Do convite ao primeiro alerta, em <span className="voice">minutos.</span></h1>
          <p className="lede">Crie a conta, convide o vendedor por telefone, mapeie ao owner do HubSpot. Ele aceita no WhatsApp respondendo “Aceito”.</p>
        </div>
        <p className="note">Consentimento registrado com versão do texto e data (LGPD).</p>
      </aside>
      <main className="auth-main"><AuthForm mode="signup" /></main>
    </div>
  );
}
