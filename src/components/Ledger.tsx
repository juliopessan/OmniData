import type { ReactNode } from "react";

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="eyebrow">{children}</p>;
}

/** Barra pareada: clay = total produzido/gap, mint = porção comprovada. */
export function Bar({ label, value, width, tone }: { label: string; value: string; width: number; tone: "clay" | "mint" | "dim" }) {
  const bg = tone === "clay" ? "var(--clay)" : tone === "mint" ? "var(--ledger-mint)" : "var(--ledger-dim)";
  return (
    <div className="bar-row">
      <div className="bar-label"><span>{label}</span><b>{value}</b></div>
      <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.min(100, Math.max(0, width * 100))}%`, background: bg }} /></div>
    </div>
  );
}

export function Fig({ value, label }: { value: string; label: string }) {
  return <div className="fig"><b>{value}</b><span>{label}</span></div>;
}

export function Measured({ children, k = "Medido, não estimado" }: { children: ReactNode; k?: string }) {
  return (
    <div className="measured">
      <span className="tick" aria-hidden="true">✓</span>
      <p><span className="k">{k}</span>{children}</p>
    </div>
  );
}

export function Flag({ k, children }: { k: string; children: ReactNode }) {
  return <div className="flag"><span className="flag-k">{k}</span><p>{children}</p></div>;
}
