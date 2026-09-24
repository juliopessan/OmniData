"use client";

import { useEffect, useRef, useState } from "react";
import { Eyebrow, Bar, Measured } from "@/components/Ledger";
import { Chat } from "@/components/Chat";
import { TEAM } from "@/lib/team";

/** "Filme" de cinco cenas que conta o produto em ritmo de motion design: texto entrando em sequência, uma
 * frase riscada, um chip de tinta, o mesmo mini-chat e o mesmo painel `.ledger` que já aparecem na página —
 * nada de componente novo, só o texto entrando em cena. Clay/mint mantêm o significado do Ledger (não
 * verificado / medido); tudo o mais é tinta sobre papel. Cada cena remonta ao entrar; as animações são CSS. */

const SCENES = [
  { label: "O vendedor não abre o CRM", ms: 3600 },
  { label: "Mas responde o WhatsApp", ms: 3800 },
  { label: "Orion decide", ms: 4600 },
  { label: "Nunca um número inventado", ms: 4600 },
  { label: "É assinada", ms: 4200 },
];

function CountUp({ to, ms }: { to: number; ms: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.textContent = String(to).padStart(2, "0");
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const k = Math.min(1, (now - t0) / ms);
      const eased = 1 - Math.pow(1 - k, 3);
      el.textContent = String(Math.round(eased * to)).padStart(2, "0");
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [to, ms]);
  return <span ref={ref}>00</span>;
}

function Scene({ index, stalled }: { index: number; stalled: number }) {
  switch (index) {
    case 0:
      return (
        <div className="fm-scene">
          <p className="fm-big fm-in">O vendedor não abre o CRM.</p>
          <p className="fm-big fm-soft fm-in" style={{ animationDelay: "0.7s" }}>
            Atualiza na sexta à noite — se lembrar.
          </p>
          <p className="fm-meta fm-in" style={{ animationDelay: "0.3s" }}>
            negócios parados <CountUp to={stalled} ms={1400} />
          </p>
        </div>
      );
    case 1:
      return (
        <div className="fm-scene">
          <p className="fm-big fm-in">A resposta não é</p>
          <p className="fm-big fm-in" style={{ animationDelay: "0.4s" }}>
            <span className="fm-strike">mais um sistema pra abrir.</span>
          </p>
          <p className="fm-big fm-in" style={{ animationDelay: "1.6s" }}>
            <span className="fm-chip">É o WhatsApp que ele já teria aberto.</span>
          </p>
        </div>
      );
    case 2:
      return (
        <div className="fm-scene fm-split">
          <div>
            <p className="eyebrow fm-in">Orion decide</p>
            <p className="fm-mid fm-in" style={{ animationDelay: "0.2s" }}>
              Uma pergunta, duas partes. Orion divide entre os especialistas certos — no máximo três passos,
              nunca mais de uma escrita.
            </p>
          </div>
          <div className="fm-in" style={{ animationDelay: "0.15s", position: "relative" }}>
            <span className="tag" style={{ position: "absolute", right: 0, top: -26 }}>exemplo</span>
            <Chat title="Ana Souza" msgs={[
              { me: true, text: "como estou na meta e anota na Acme que o CFO aprovou" },
              {
                text: <><b>Vega</b>: Você está em <b>82%</b> da meta. Falta <b>R$ 72.000</b>.<br /><br /><b>Lyra</b>: Registrei ✅ <b>Nota</b> em <b>Acme – Renovação</b>.</>,
                buttons: ["Editar", "Desfazer"],
              },
            ]} />
          </div>
        </div>
      );
    case 3:
      return (
        <div className="fm-scene fm-split">
          <div>
            <p className="eyebrow fm-in">Nunca um número inventado</p>
            <p className="fm-mid fm-in" style={{ animationDelay: "0.2s" }}>
              Se o texto trouxer um valor que não veio da ferramenta, a resposta é descartada antes de chegar
              até você. Argus avisa quando a amostra é baixa demais pra confiar.
            </p>
          </div>
          <div className="ledger fm-in" style={{ animationDelay: "0.15s" }}>
            <div className="ledger-head"><span className="live">Resposta da Vega</span><span className="meta">exemplo</span></div>
            <Bar label="Meta do time" value="R$ 400.000" width={1} tone="dim" />
            <Bar label="Ganho no período" value="R$ 391.000" width={0.98} tone="mint" />
            <Measured>Calculado em SQL a partir do HubSpot. O modelo nunca escreve o número — só narra o que a ferramenta devolveu.</Measured>
          </div>
        </div>
      );
    default:
      return (
        <div className="fm-scene">
          <p className="fm-big fm-in">Não é uma resposta genérica.</p>
          <p className="fm-big fm-in" style={{ animationDelay: "0.6s" }}>
            É <span className="voice">assinada</span>.
          </p>
          <div className="fm-team fm-in" style={{ animationDelay: "1.3s" }} aria-hidden="true">
            {TEAM.members.map((m, i) => (
              <span key={m.key} className="fm-team-item fm-in" style={{ animationDelay: `${1.4 + i * 0.09}s` }}>
                <span className="mono-tile sm">{m.name.slice(0, 2)}</span>
                <span className="mono">{m.name}</span>
              </span>
            ))}
          </div>
          <p className="fm-meta fm-in" style={{ animationDelay: "2.4s" }}>
            {TEAM.members.length} especialistas · cada um só com as próprias ferramentas
          </p>
        </div>
      );
  }
}

export function StoryFilm({ stalled }: { stalled: number }) {
  const [scene, setScene] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [visible, setVisible] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Sem movimento: começa pausado; as cenas continuam navegáveis pelos segmentos.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) setPlaying(false);
    const el = root.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!playing || !visible) return;
    const id = window.setTimeout(() => setScene((s) => (s + 1) % SCENES.length), SCENES[scene].ms);
    return () => window.clearTimeout(id);
  }, [scene, playing, visible]);

  const running = playing && visible;

  return (
    <div ref={root} className="fm" aria-roledescription="apresentação" aria-label="Como o Observatório funciona, em cinco cenas">
      <div className="fm-stage" key={scene}>
        <Scene index={scene} stalled={stalled} />
      </div>
      <div className="fm-controls">
        <div className="fm-segs">
          {SCENES.map((s, i) => (
            <button
              key={s.label}
              type="button"
              className="fm-seg"
              data-state={i < scene ? "done" : i === scene ? "active" : "idle"}
              data-running={running || undefined}
              style={{ "--fm-d": `${s.ms}ms` } as React.CSSProperties}
              onClick={() => setScene(i)}
              aria-label={`Cena ${i + 1}: ${s.label}`}
              aria-current={i === scene ? "step" : undefined}
            >
              <span className="fm-seg-fill" />
            </button>
          ))}
        </div>
        <button type="button" className="fm-play mono" onClick={() => setPlaying((p) => !p)}>
          {playing ? "pausar" : "tocar"}
        </button>
      </div>
    </div>
  );
}
