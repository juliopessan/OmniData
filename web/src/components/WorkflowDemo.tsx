"use client";

import { useEffect, useRef, useState } from "react";

/** Versão animada da sequência "Do CRM ao WhatsApp em quatro passos": a régua de cada card enche enquanto o
 * passo está ativo, e um painel `.ledger` mostra um negócio de exemplo passando pelas quatro etapas. Mesmo
 * texto de sempre — só ganhou movimento. */

const STEPS = [
  { n: "01", t: "Ingestão", d: "Sincroniza o HubSpot a cada 15 minutos: negócios, contatos, atividades e histórico de etapas." },
  { n: "02", t: "Métricas em SQL", d: "Win rate com intervalo de confiança, cobertura de meta e saúde do negócio, calculados e nunca “estimados” pelo modelo." },
  { n: "03", t: "Plano do Orion", d: "O modelo propõe até 3 passos; o código valida quem pode chamar o quê. No máximo uma escrita, e por último." },
  { n: "04", t: "Resposta assinada", d: "Cada especialista escreve a sua parte. Toda escrita tem recibo e Desfazer por 24h; as sensíveis pedem confirmação." },
];

const DURATIONS = [2200, 3000, 3000, 2600, 2200];
const LAST = STEPS.length;

export function WorkflowDemo() {
  const [phase, setPhase] = useState(0);
  const [visible, setVisible] = useState(false);
  const [reduced, setReduced] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setReduced(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const el = root.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.3 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (reduced || !visible) return;
    const id = window.setTimeout(() => setPhase((p) => (p + 1) % (LAST + 1)), DURATIONS[phase]);
    return () => window.clearTimeout(id);
  }, [phase, visible, reduced]);

  const p = reduced ? LAST : phase; // sem movimento: mostra direto o estado final, completo

  return (
    <div ref={root}>
      <div className="seq">
        {STEPS.map((s, i) => {
          const state = i < p ? "done" : i === p ? "active" : "idle";
          return (
            <div key={s.n} className="wf-step" data-state={state} style={{ "--wf-d": `${DURATIONS[i]}ms` } as React.CSSProperties}>
              <div className="wf-track"><span className="wf-fill" /></div>
              <span className="n">{s.n}</span>
              <h3 className="h3">{s.t}</h3>
              <p className="body">{s.d}</p>
            </div>
          );
        })}
      </div>

      {/* Painel ilustrativo: um negócio de exemplo passando pelos quatro passos. Decorativo (repete em loop) —
          o conteúdo real já está nos cards acima. */}
      <div className="ledger" style={{ marginTop: 32 }} aria-hidden="true">
        <div className="ledger-head"><span className="live">Um negócio, do HubSpot ao WhatsApp</span><span className="meta">exemplo ilustrativo</span></div>
        <div className="wf-log">
          <p className="wf-line" data-on={p >= 0 || undefined}>
            <span className="wf-k">ingestão</span>
            Acme – Renovação sincronizado do HubSpot · etapa Proposta
          </p>
          <p className="wf-line" data-on={p >= 1 || undefined}>
            <span className="wf-k">métricas</span>
            {p === 1 ? "calculando win rate, IC 95% e saúde do negócio…" : "68% de win rate (IC 52%–81%) · negócio marcado como parado"}
          </p>
          <div className="wf-line" data-on={p >= 1 || undefined}>
            <div className={p >= 3 ? "resolved wf-flip" : "flag"}>
              {p >= 3 ? (
                <>
                  <span className="resolved-k">Altair → Lyra · próximo passo registrado</span>
                  <p style={{ color: "var(--ledger-ink)" }}>Nota do CFO virou próximo passo, com recibo e Desfazer por 24h.</p>
                </>
              ) : (
                <>
                  <span className="flag-k">Altair · sem próximo passo</span>
                  <p style={{ color: "var(--ledger-ink)" }}>Negócio parado há 41 dias, sem próximo passo registrado.</p>
                </>
              )}
            </div>
          </div>
          <p className="wf-line" data-on={p >= 2 || undefined}>
            <span className="wf-k">orion</span>
            {p === 2 ? "decidindo quem responde…" : "plano validado: Vega + Lyra, no máximo uma escrita"}
          </p>
          <p className="wf-line" data-on={p >= 3 || undefined}>
            <span className="wf-k">entrega</span>
            resposta enviada no WhatsApp, assinada por Vega e Lyra
          </p>
        </div>
      </div>
    </div>
  );
}
