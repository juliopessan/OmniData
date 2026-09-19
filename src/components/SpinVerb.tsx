"use client";
import { useEffect, useState } from "react";

const FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
export const VERBS = ["Sincronizando", "Reconciliando", "Calibrando", "Pontuando", "Auditando", "Cruzando", "Simulando", "Rastreando", "Ingerindo"];

/** Spinner + verbo rotativo (estilo terminal). Respeita prefers-reduced-motion. */
export function SpinVerb({ verbs = VERBS, interval = 1900, onDark = false, label }: {
  verbs?: string[]; interval?: number; onDark?: boolean; label?: string;
}) {
  const [f, setF] = useState(0);
  const [v, setV] = useState(0);
  const [still, setStill] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setStill(mq.matches);
    if (mq.matches) return;
    const a = setInterval(() => setF((x) => (x + 1) % FRAMES.length), 80);
    const b = setInterval(() => setV((x) => (x + 1) % verbs.length), interval);
    return () => { clearInterval(a); clearInterval(b); };
  }, [verbs.length, interval]);
  return (
    <span className={`spinverb${onDark ? " on-dark" : ""}`} role="status" aria-live="polite">
      <span className="glyph" aria-hidden="true">{still ? "·" : FRAMES[f]}</span>
      <span className="verb">{verbs[v]}</span>
      <span className="dots" aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  );
}
