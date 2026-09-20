/** Fila de correção do Coach (Polaris). Porta em TypeScript de src/omnidata/hygiene/compute.py; as regras vêm de hygiene-spec.json. */
import spec from "./hygiene-spec.json";
import type { Deal } from "./seed";
import type { Rec } from "./insights";
import { statusOf } from "./metrics";

export interface Issue { code: string; label: string; who: string; deals: number; share: number; systemic: boolean }
export interface QueueRow { id: string; name: string; amount: number; issues: string[]; firstFix: string; tool: string }
export interface FixQueue {
  openDeals: number; clean: number; issues: Issue[]; systemic: string[]; queue: QueueRow[]; queueTotal: number; notesKnown: boolean;
  managerInactive: { id: string; name: string; owner: string }[]; managerDuplicates: { name: string; deals: number }[];
}

const S = spec.issues as { code: string; label: string; who: string; tool: string; how: string }[];
const META = Object.fromEntries(S.map((i) => [i.code, i]));
const norm = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
const key = (s: string) => norm(s).replace(/[^\p{L}\p{N}]+/gu, "");
const DEMAND = /\[[^\[\]]+\]\s*$|\s[–—-]\s\S/;

export function nameOk(name: string): boolean {
  const n = name.trim();
  return (n.split("[").length === n.split("]").length) && DEMAND.test(n);
}

/** `recs` traz as notas (só existe para arquivo enviado). Sem ele, "sem nota" não é avaliado. */
export function fixQueue(deals: Deal[], recs: Rec[] | undefined, limit = 8): FixQueue {
  const open = deals.filter((d) => statusOf(d) === "open");
  const notes = new Map((recs ?? []).map((r) => [r.id, r.notes.length]));
  const notesKnown = !!recs?.length;
  const groups = new Map<string, string[]>();
  for (const d of open) (groups.get(key(d.name)) ?? groups.set(key(d.name), []).get(key(d.name))!).push(d.id);
  const dup = new Set([...groups.values()].filter((v) => v.length > 1).flat());
  const per = new Map<string, string[]>();
  for (const d of open) {
    const f: string[] = [];
    if (!d.amount) f.push("no_amount");
    if (d.overdue) f.push("close_date_past");
    if (!d.nextStep) f.push("no_next_step");
    if (notesKnown && !(notes.get(d.id) ?? 0)) f.push("no_notes");
    if (!nameOk(d.name)) f.push("name_format");
    if (/deactivated|desativad/i.test(d.owner)) f.push("owner_inactive");
    if (dup.has(d.id)) f.push("duplicate");
    per.set(d.id, f);
  }
  const n = open.length;
  const count = (c: string) => [...per.values()].filter((v) => v.includes(c)).length;
  const issues: Issue[] = S.filter((i) => count(i.code)).map((i) => ({ code: i.code, label: i.label, who: i.who, deals: count(i.code), share: count(i.code) / n, systemic: n > 0 && count(i.code) / n >= spec.systemicShare }));
  const systemic = issues.filter((i) => i.systemic).map((i) => i.code);
  const rows = open.map((d) => ({ d, fx: per.get(d.id)!.filter((c) => META[c].who === "seller" && (!systemic.includes(c) || d.amount > 0)) })).filter((r) => r.fx.length);
  rows.sort((a, b) => b.d.amount - a.d.amount || b.fx.length - a.fx.length || a.d.name.localeCompare(b.d.name, "pt-BR"));
  return {
    openDeals: n, clean: [...per.values()].filter((v) => !v.length).length, issues, systemic, notesKnown, queueTotal: rows.length,
    queue: rows.slice(0, limit).map(({ d, fx }) => ({ id: d.id, name: d.name, amount: d.amount, issues: fx, firstFix: META[fx[0]].how, tool: META[fx[0]].tool })),
    managerInactive: open.filter((d) => per.get(d.id)!.includes("owner_inactive")).slice(0, limit).map((d) => ({ id: d.id, name: d.name, owner: d.owner })),
    managerDuplicates: [...groups.values()].filter((v) => v.length > 1).slice(0, limit).map((ids) => ({ name: open.find((d) => d.id === ids[0])!.name, deals: ids.length })),
  };
}
