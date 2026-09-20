/** Gráficos do Modo reunião. SVG/HTML sem biblioteca, no padrão Ledger: tinta e traço fino; clay só para lacuna; nunca mint. */
import type { ReactNode } from "react";

export interface BarRow { label: string; value: number; display: string; note?: ReactNode }

/** Barras horizontais. O comprimento é sempre relativo ao maior valor da lista; o número exato fica escrito ao lado. */
export function HBars({ rows, label, gap = false }: { rows: BarRow[]; label: string; gap?: boolean }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="hbars" role="img" aria-label={`${label}: ${rows.map((r) => `${r.label} ${r.display}`).join("; ")}`}>
      {rows.map((r) => (
        <div className="hbar" key={r.label}>
          <span className="hbar-l" title={r.label}>{r.label}</span>
          <svg className="hbar-t" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
            <rect x="0" y="0" width="100" height="10" className="trk" />
            <rect x="0" y="0" width={Math.max(0.6, (r.value / max) * 100)} height="10" className={gap ? "fill gap" : "fill"} />
          </svg>
          <span className="hbar-v">{r.display}</span>
          {r.note && <span className="hbar-n">{r.note}</span>}
        </div>
      ))}
    </div>
  );
}

/** Uma barra dividida em duas partes: a parte completa (tinta) e a lacuna (clay). */
export function SplitBar({ done, gap, doneLabel, gapLabel }: { done: number; gap: number; doneLabel: string; gapLabel: string }) {
  const total = Math.max(1, done + gap);
  const w = (done / total) * 100;
  return (
    <figure className="split" aria-label={`${doneLabel}: ${done}; ${gapLabel}: ${gap}`}>
      <svg viewBox="0 0 100 12" preserveAspectRatio="none" aria-hidden="true">
        <rect x="0" y="0" width={w} height="12" className="fill" />
        <rect x={w} y="0" width={100 - w} height="12" className="fill gap" />
      </svg>
      <figcaption><span><i className="sw" />{doneLabel} <b>{done.toLocaleString("pt-BR")}</b></span><span><i className="sw gap" />{gapLabel} <b>{gap.toLocaleString("pt-BR")}</b></span></figcaption>
    </figure>
  );
}

/** Anel de cobertura (0 a 1). Valor ausente aparece como "n/d", nunca como zero. */
export function Ring({ value, label }: { value: number | null; label: string }) {
  const r = 15.9155, c = 2 * Math.PI * r;
  return (
    <figure className="ring" aria-label={`${label}: ${value === null ? "n/d" : Math.round(value * 100) + "%"}`}>
      <svg viewBox="0 0 36 36" aria-hidden="true">
        <circle cx="18" cy="18" r={r} className="trk" />
        {value !== null && <circle cx="18" cy="18" r={r} className="arc" strokeDasharray={`${Math.max(0, Math.min(1, value)) * c} ${c}`} transform="rotate(-90 18 18)" />}
      </svg>
      <b>{value === null ? "—" : `${Math.round(value * 100)}%`}</b>
      <figcaption>{label}</figcaption>
    </figure>
  );
}

export interface RangeRow { label: string; lo: number; mid: number; hi: number; display: string }

/** Faixas de incerteza: a barra vai do pior provável ao melhor provável (10%–90%), o traço marca a mediana e a linha tracejada a meta. */
export function RangeBars({ rows, max, target, label }: { rows: RangeRow[]; max: number; target?: number | null; label: string }) {
  const x = (v: number) => (max > 0 ? Math.min(100, Math.max(0, (v / max) * 100)) : 0);
  return (
    <div className="hbars" role="img" aria-label={`${label}: ${rows.map((r) => `${r.label} ${r.display}`).join("; ")}${target ? `; meta ${Math.round(target)}` : ""}`}>
      {rows.map((r) => (
        <div className="hbar" key={r.label}>
          <span className="hbar-l">{r.label}</span>
          <svg className="hbar-t range" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
            <rect x="0" y="3" width="100" height="4" className="trk" />
            <rect x={x(r.lo)} y="2" width={Math.max(0.6, x(r.hi) - x(r.lo))} height="6" className="fill" />
            <rect x={x(r.mid) - 0.3} y="0" width="0.6" height="10" className="mid" />
            {target ? <line x1={x(target)} x2={x(target)} y1="0" y2="10" className="tgt" vectorEffect="non-scaling-stroke" /> : null}
          </svg>
          <span className="hbar-v">{r.display}</span>
        </div>
      ))}
    </div>
  );
}
