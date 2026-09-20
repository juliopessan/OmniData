/** Previsão estatística do pipeline aberto. Porta de src/omnidata/forecast/compute.py: mesmas regras, mesmo gerador de números
 *  (mulberry32 com semente fixa), então os números do navegador e do bot coincidem. Arquivo autônomo (sem imports) de propósito:
 *  os testes o executam no Node e comparam com o Python. */
export const SPEC = { minClosed: 10, indicativeClosed: 20, trials: 4000, maxDraws: 4_000_000, minTrials: 200, seed: 20260920, backlogRatio: 3 };

export interface Scenario { p: number; expected: number; p10: number; p50: number; p90: number; probTarget?: number }
export interface Forecast {
  status: "insufficient" | "no_pipeline" | "indicative" | "ok";
  closed: number; wins: number; losses: number; openWithValue: number; openAmount: number; realized: number; quota: number | null;
  backlog?: boolean; winRate?: number; winRateCi?: [number, number]; trials?: number; target?: number | null;
  scenarios?: { low: Scenario; mid: Scenario; high: Scenario };
}

export function mulberry32(seed: number): () => number {
  let a = seed | 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function wilson(wins: number, n: number, z = 1.96): [number, number] {
  if (n <= 0) return [0, 0];
  const p = wins / n, denom = 1 + (z * z) / n, centre = p + (z * z) / (2 * n);
  const margin = z * Math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n);
  return [(centre - margin) / denom, (centre + margin) / denom];
}

const quantile = (sorted: number[], q: number) => sorted[Math.floor(q * (sorted.length - 1))];

function totals(amounts: number[], p: number, trials: number, seed: number): number[] {
  const rnd = mulberry32(seed);
  const out: number[] = [];
  for (let i = 0; i < trials; i++) {
    let s = 0;
    for (const a of amounts) if (rnd() < p) s += a;
    out.push(s);
  }
  return out;
}

export function forecast(openAmounts: number[], wins: number, losses: number, realized = 0, quota: number | null = null): Forecast {
  const amounts = openAmounts.filter((a) => a > 0).sort((x, y) => y - x);
  const closed = wins + losses;
  const openAmount = amounts.reduce((s, a) => s + a, 0);
  const base = { closed, wins, losses, openWithValue: amounts.length, openAmount, realized, quota };
  if (closed < SPEC.minClosed) return { ...base, status: "insufficient" };
  if (!amounts.length) return { ...base, status: "no_pipeline" };
  const [lo, hi] = wilson(wins, closed);
  const rate = wins / closed;
  const target = quota !== null ? Math.max(quota - realized, 0) : null;
  const trials = Math.min(SPEC.trials, Math.max(SPEC.minTrials, Math.floor(SPEC.maxDraws / amounts.length)));
  const sc = (p: number): Scenario => {
    const t = totals(amounts, p, trials, SPEC.seed).sort((x, y) => x - y);
    const s: Scenario = { p, expected: p * openAmount, p10: quantile(t, 0.1), p50: quantile(t, 0.5), p90: quantile(t, 0.9) };
    if (target !== null) s.probTarget = target <= 0 ? 1 : t.filter((x) => x >= target).length / t.length;
    return s;
  };
  const backlog = amounts.length > SPEC.backlogRatio * closed; // muito mais abertos que fechados: a taxa do passado superestima o acúmulo
  return { ...base, status: closed < SPEC.indicativeClosed || backlog ? "indicative" : "ok", backlog, winRate: rate, winRateCi: [lo, hi], trials, target,
    scenarios: { low: sc(lo), mid: sc(rate), high: sc(hi) } };
}
