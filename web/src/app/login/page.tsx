import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/Logo";
import { SpinVerb } from "@/components/SpinVerb";
import { AuthForm } from "@/components/AuthForm";

export const metadata: Metadata = { title: "Entrar" };

export default function Login() {
  return (
    <div className="auth">
      <aside className="auth-side">
        <Link href="/" style={{ color: "var(--ledger-ink)" }}><Logo /></Link>
        <div className="stack" style={{ gap: 18 }}>
          <SpinVerb onDark verbs={["Sincronizando", "Reconciliando", "Auditando", "Calibrando"]} label="pipeline da semana" />
          <h1 className="h2">Bom te ver de <span className="voice">volta.</span></h1>
          <p className="lede">Entre para ver o resultado do time, os alertas do dia e a qualidade dos dados.</p>
        </div>
        <p className="note">© OmniData · dados de demonstração</p>
      </aside>
      <main className="auth-main">
        <AuthForm mode="login" />
      </main>
    </div>
  );
}
