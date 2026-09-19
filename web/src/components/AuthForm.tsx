"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { SpinVerb } from "./SpinVerb";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const signup = mode === "signup";
  function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setTimeout(() => router.push("/dashboard"), 1800);
  }
  return (
    <form className="auth-form" onSubmit={submit}>
      <div className="stack" style={{ gap: 6 }}>
        <h2 className="h2" style={{ fontSize: 30 }}>{signup ? "Criar conta" : "Entrar"}</h2>
        <p className="body">{signup ? "Sem cartão. Comece com dados sintéticos." : "Acesse o painel do seu time."}</p>
      </div>
      {signup && <div className="field"><label htmlFor="org">Empresa</label><input id="org" required placeholder="Acme Ltda." autoComplete="organization" /></div>}
      <div className="field"><label htmlFor="email">E-mail</label><input id="email" type="email" required placeholder="voce@empresa.com" autoComplete="email" /></div>
      <div className="field"><label htmlFor="pw">Senha</label><input id="pw" type="password" required minLength={8} autoComplete={signup ? "new-password" : "current-password"} /></div>
      <button className="btn" disabled={busy} type="submit">
        {busy ? <SpinVerb onDark={false} verbs={signup ? ["Criando", "Provisionando", "Calibrando"] : ["Autenticando", "Sincronizando", "Reconciliando"]} /> : signup ? "Criar conta →" : "Entrar →"}
      </button>
      <p className="note">Demonstração: não há autenticação real nem envio de dados. {signup ? <>Já tem conta? <Link href="/login" style={{ textDecoration: "underline" }}>Entrar</Link></> : <>Novo por aqui? <Link href="/cadastro" style={{ textDecoration: "underline" }}>Criar conta</Link></>}</p>
    </form>
  );
}
