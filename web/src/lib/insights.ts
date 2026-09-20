import spec from "./insights-spec.json";
import { norm } from "./datasets";

/** Port de src/omnidata/insights/compute.py (mesmos dicionários, vindos de insights-spec.json). Só contagens: sem LLM. */
export interface Rec { id: string; name: string; status: "open" | "won" | "lost"; amount: number; campaign: string | null; reason: string | null; notes: string[] }
export interface Group { key: string; deals: number; open: number; won: number; lost: number; closed: number; winRate: number | null; lowN: boolean; openAmount: number }

const MIN_N = 20;
const sysCfg = spec.systems as Record<string, { category: string; aliases: string[] }>;
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const SYS = Object.entries(sysCfg).map(([name, c]) => ({ name, category: c.category, res: c.aliases.map((a) => new RegExp(`(?<![a-z0-9])${esc(a)}(?![a-z0-9])`)) }));
const PAIN = new RegExp(spec.painLabels, "i");
const CUES = spec.painCues.map((c) => new RegExp(c, "i"));
const ROLES = Object.entries(spec.rolePatterns as Record<string, string>).map(([k, p]) => [k, new RegExp(p, "i")] as const);
const STOP = new Set(spec.stopwords);
const DEMAND_SPLIT = new RegExp(spec.demandSplit);
const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0); // ordem por ponto de código, como o Python

const rate = (w: number, l: number) => (w + l ? w / (w + l) : null);
export const painsOf = (r: Rec): string[] => {
  const out: string[] = [];
  for (const n of r.notes) {
    const m = PAIN.exec(n);
    if (m) { out.push(m[1].trim().replace(/\.$/, "")); continue; }
    for (const rx of CUES) { const c = rx.exec(n); if (c) { out.push(c[1].trim().replace(/\.$/, "")); break; } }
  }
  return out;
};

export function systemsOf(r: Rec): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>();
  const add = (s: string, role: string) => out.set(s, (out.get(s) ?? new Set()).add(role));
  for (const t of [...r.notes, ...(r.reason ? [r.reason] : [])]) {
    const n = norm(t);
    for (const s of SYS) if (s.res.some((rx) => rx.test(n))) add(s.name, "mention");
    for (const [role, rx] of ROLES) {
      const m = rx.exec(t);
      if (m) { const n2 = norm(m[1]); for (const s of SYS) if (s.res.some((x) => x.test(n2))) add(s.name, role); }
    }
  }
  return out;
}

const DEMAND_BRACKET = new RegExp(spec.demandBracket);
const COMPANY_SPLIT = new RegExp(spec.companySplit);
const MENTION = new RegExp(spec.mention, "g");
const parts = (name: string) => name.trim().split(DEMAND_SPLIT);
export const demandType = (name: string) => {
  const m = DEMAND_BRACKET.exec(name.trim());
  if (m && m[1].trim()) return m[1].trim();
  const p = parts(name); return p.length >= 2 && p[p.length - 1].trim() ? p[p.length - 1].trim() : null;
};
const company = (name: string) => {
  const n = name.trim();
  if (n.includes("<>")) return n.split(COMPANY_SPLIT)[0].trim() || null;
  const p = parts(name); return p.length >= 2 ? p[0].trim() : null;
};
const lastWord = (name: string) => (company(name) ?? "").split(" ").pop() ?? "";

export function classifyLoss(reason: string): { code: string; label: string } {
  const n = norm(reason);
  for (const t of spec.lossTaxonomy) if (t.keywords.some((k) => n.includes(k))) return { code: t.code, label: t.label };
  return { code: "other", label: "Outro" };
}

function groupStats(recs: Rec[], key: (r: Rec) => string | null): Group[] {
  const g = new Map<string, Rec[]>();
  for (const r of recs) { const k = key(r); if (k) g.set(k, [...(g.get(k) ?? []), r]); }
  return [...g].map(([k, rs]) => {
    const won = rs.filter((r) => r.status === "won").length, lost = rs.filter((r) => r.status === "lost").length;
    return { key: k, deals: rs.length, open: rs.filter((r) => r.status === "open").length, won, lost, closed: won + lost, winRate: rate(won, lost), lowN: won + lost < MIN_N,
      openAmount: rs.filter((r) => r.status === "open").reduce((s, r) => s + r.amount, 0) };
  }).sort((a, b) => b.deals - a.deals || cmp(a.key, b.key));
}

const keep = (k: string, w: string) => w.length >= 4 && !STOP.has(k);
export function terms(recs: Rec[], limit: number) {
  const uni = new Map<string, Set<number>>(), bi = new Map<string, Set<number>>(), disp = new Map<string, string>();
  const put = (m: Map<string, Set<number>>, k: string, i: number, d: string) => { (m.get(k) ?? m.set(k, new Set()).get(k)!).add(i); if (!disp.has(k)) disp.set(k, d); };
  recs.forEach((r, i) => {
    for (const note of r.notes) for (const sent of note.replace(MENTION, " ").split(/[.;:!?|\n]+/)) {
      if (!sent.trim()) continue;
      const toks = (sent.toLowerCase().match(/[a-zà-ú]+/g) ?? []).map((w) => [norm(w), w] as const);
      for (const [k, w] of toks) if (keep(k, w)) put(uni, k, i, w);
      for (let j = 0; j + 1 < toks.length; j++) if (keep(...toks[j]) && keep(...toks[j + 1])) put(bi, `${toks[j][0]} ${toks[j + 1][0]}`, i, `${toks[j][1]} ${toks[j + 1][1]}`);
    }
  });
  const rank = (d: Map<string, Set<number>>) => [...d].filter(([, s]) => s.size >= 3).map(([k, idx]) => {
    const won = [...idx].filter((i) => recs[i].status === "won").length, lost = [...idx].filter((i) => recs[i].status === "lost").length;
    return { term: disp.get(k)!, deals: idx.size, won, lost, winRate: won + lost >= 10 ? rate(won, lost) : null };
  }).sort((a, b) => b.deals - a.deals || cmp(a.term, b.term)).slice(0, limit);
  return { words: rank(uni), phrases: rank(bi) };
}

export function analyze(recs: Rec[], limit = 10) {
  const n = recs.length;
  const painBy = new Map<string, Rec[]>(), painDisp = new Map<string, string>();
  for (const r of recs) {
    const mine = new Map<string, string>();
    for (const p of painsOf(r)) mine.set(norm(p), p);
    for (const [k, p] of mine) { painBy.set(k, [...(painBy.get(k) ?? []), r]); if (!painDisp.has(k)) painDisp.set(k, p); }
  }
  const withPain = new Set([...painBy.values()].flat().map((r) => r.id)).size;
  const pains = [...painBy].map(([k, rs]) => {
    const won = rs.filter((r) => r.status === "won").length, lost = rs.filter((r) => r.status === "lost").length;
    return { pain: painDisp.get(k)!, deals: rs.length, share: withPain ? rs.length / withPain : 0, closed: won + lost, winRate: won + lost >= 10 ? rate(won, lost) : null };
  }).sort((a, b) => b.deals - a.deals || cmp(a.pain, b.pain));

  const sysBy = new Map<string, { mention: Rec[]; won_against: number; internal: number }>();
  for (const r of recs) for (const [s, roles] of systemsOf(r)) {
    const e = sysBy.get(s) ?? { mention: [], won_against: 0, internal: 0 };
    e.mention.push(r); if (roles.has("won_against")) e.won_against++; if (roles.has("internal")) e.internal++;
    sysBy.set(s, e);
  }
  const systems = [...sysBy].map(([s, e]) => {
    const won = e.mention.filter((r) => r.status === "won").length, lost = e.mention.filter((r) => r.status === "lost").length;
    return { system: s, category: sysCfg[s].category, deals: e.mention.length, wonAgainst: e.won_against, internal: e.internal, closed: won + lost, winRate: won + lost >= 10 ? rate(won, lost) : null };
  }).sort((a, b) => b.deals - a.deals || cmp(a.system, b.system));

  const segCounts = new Map<string, number>();
  for (const r of recs) if (company(r.name)) segCounts.set(lastWord(r.name), (segCounts.get(lastWord(r.name)) ?? 0) + 1);
  const segOk = new Set([...segCounts].filter(([w, c]) => c >= spec.minSegmentDeals && /^\p{L}+$/u.test(w)).map(([w]) => w));
  const lostRecs = recs.filter((r) => r.status === "lost" && r.reason);
  const tax = new Map<string, { label: string; deals: number }>();
  for (const r of lostRecs) { const c = classifyLoss(r.reason!); const e = tax.get(c.code) ?? { label: c.label, deals: 0 }; e.deals++; tax.set(c.code, e); }
  const nLost = recs.filter((r) => r.status === "lost").length;
  const cov = (k: number, base: number) => (base ? k / base : null);
  return {
    coverage: { deals: n, withNotes: cov(recs.filter((r) => r.notes.length).length, n), withPain: cov(withPain, n), withSystem: cov(recs.filter((r) => systemsOf(r).size).length, n),
      withDemand: cov(recs.filter((r) => demandType(r.name)).length, n), withCampaign: cov(recs.filter((r) => r.campaign).length, n), lostWithReason: cov(lostRecs.length, nLost), lost: nLost },
    pains: { withPain, lowN: withPain < MIN_N, items: pains.slice(0, limit) },
    terms: terms(recs, limit),
    demand: groupStats(recs, (r) => demandType(r.name)).slice(0, limit),
    systems: { all: systems.slice(0, limit * 2), erp: systems.filter((s) => s.category === "erp").slice(0, limit), crm: systems.filter((s) => s.category === "crm").slice(0, limit) },
    segments: groupStats(recs, (r) => (segOk.has(lastWord(r.name)) ? lastWord(r.name) : null)).slice(0, limit),
    campaigns: groupStats(recs, (r) => r.campaign).slice(0, limit),
    lossTaxonomy: [...tax].map(([code, v]) => ({ code, ...v })).sort((a, b) => b.deals - a.deals || cmp(a.code, b.code)),
    lost: nLost,
  };
}
export type Analysis = ReturnType<typeof analyze>;
export const OWNERS = spec.owners as Record<string, string>;
