import { deals, owners, STAGE_P75, STAGE_PROB, MIN_N_RANKING, type Deal } from "./seed";

export const brl = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n);
export const pct = (n: number, digits = 1) => `${(n * 100).toFixed(digits).replace(".", ",")}%`;
export const pad2 = (n: number) => String(n).padStart(2, "0");

/** Intervalo de Wilson 95% (PRD §10.1). */
export function wilson(wins: number, n: number, z = 1.96): [number, number] {
  if (!n) return [0, 0];
  const p = wins / n;
  const denom = 1 + (z * z) / n;
  const centre = p + (z * z) / (2 * n);
  const margin = z * Math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n);
  return [(centre - margin) / denom, (centre + margin) / denom];
}

export interface Health {
  deal: Deal;
  stalled: boolean;
  flags: string[];
  attention: number;
}

/** deal_health heurístico (FR-PRD-1): sem ML. */
export function health(d: Deal): Health {
  const p75 = STAGE_P75[d.stage] ?? 14;
  const stalled = d.daysInStage > p75;
  const flags: string[] = [];
  if (stalled) flags.push(`parado há ${d.daysInStage} dias (p75 = ${p75})`);
  if (d.overdue) flags.push("data de fechamento vencida");
  if (!d.nextStep) flags.push("sem próximo passo");
  if (d.quietDays >= 10) flags.push(`sem atividade há ${d.quietDays} dias`);
  const urgency = Math.min(1, 0.25 + (stalled ? 0.3 : 0) + (d.overdue ? 0.25 : 0) + (!d.nextStep ? 0.2 : 0));
  return { deal: d, stalled, flags, attention: d.amount * STAGE_PROB[d.stage] * urgency };
}

export function computeMetrics() {
  const won = deals.filter((d) => d.stage === "Ganho");
  const lost = deals.filter((d) => d.stage === "Perdido");
  const open = deals.filter((d) => d.stage !== "Ganho" && d.stage !== "Perdido");
  const closed = won.length + lost.length;
  const wonAmount = won.reduce((s, d) => s + d.amount, 0);
  const quota = owners.reduce((s, o) => s + o.quota, 0);
  const gap = Math.max(quota - wonAmount, 0);
  const openAmount = open.reduce((s, d) => s + d.amount, 0);
  const winRate = closed ? won.length / closed : 0;
  const [ciLow, ciHigh] = wilson(won.length, closed);
  const healthRows = open.map(health).sort((a, b) => b.attention - a.attention);
  const lostNoReason = lost.filter((d) => !d.reason);
  return {
    won, lost, open, closed, wonAmount, quota, gap, openAmount, winRate, ciLow, ciHigh,
    attainment: quota ? wonAmount / quota : 0,
    coverage: gap ? openAmount / gap : 0,
    requiredCoverage: winRate ? 1 / winRate : 0,
    lowN: closed < MIN_N_RANKING,
    healthRows,
    stalled: healthRows.filter((h) => h.stalled).length,
    noNextStep: open.filter((d) => !d.nextStep),
    lostNoReason,
    lossReasonCoverage: lost.length ? (lost.length - lostNoReason.length) / lost.length : 0,
  };
}
