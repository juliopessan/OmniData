import spec from "./dataset-spec.json";
import type { Deal } from "./seed";
import type { Rec } from "./insights";

export interface ColumnSpec { name: string; required: boolean; stored: boolean; hint: string; aliases: string[] }
export interface KindSpec { key: string; title: string; description: string; columns: ColumnSpec[] }
export const KINDS = spec.kinds as KindSpec[];

/** Mesma normalização do back-end (src/omnidata/datasets/spec.py:norm): sem acento, minúsculo, só a-z0-9. */
export const norm = (s: string) =>
  s.replace(/﻿/g, "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

export function parseCsv(text: string, maxRows = 6): { headers: string[]; rows: string[][]; total: number; delimiter: string } {
  const t = text.replace(/^﻿/, "");
  const firstLine = t.split(/\r?\n/, 1)[0] ?? "";
  const delimiter = [",", ";", "\t", "|"].reduce((a, b) => (firstLine.split(b).length > firstLine.split(a).length ? b : a), ",");
  const all: string[][] = [];
  let row: string[] = [], cell = "", q = false;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (q) {
      if (c === '"' && t[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') q = false;
      else cell += c;
    } else if (c === '"') q = true;
    else if (c === delimiter) { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && t[i + 1] === "\n") i++;
      row.push(cell); cell = "";
      if (row.some((x) => x.trim())) all.push(row);
      row = [];
    } else cell += c;
  }
  if (cell || row.length) { row.push(cell); if (row.some((x) => x.trim())) all.push(row); }
  const [headers = [], ...rows] = all;
  return { headers: headers.map((h) => h.trim()), rows: rows.slice(0, maxRows), total: rows.length, delimiter };
}

export function mapHeaders(kind: KindSpec, headers: string[]) {
  const amap = new Map<string, string>();
  for (const c of kind.columns) for (const a of c.aliases) if (!amap.has(a)) amap.set(a, c.name);
  const mapping: Record<string, string> = {};
  const ignored: string[] = [];
  for (const h of headers) {
    const canon = amap.get(norm(h));
    if (!canon) { if (h) ignored.push(h); } else if (!(canon in mapping)) mapping[canon] = h;
  }
  return { mapping, ignored, missing: kind.columns.filter((c) => c.required && !(c.name in mapping)).map((c) => c.name) };
}

export interface RowError { line: number; column: string; message: string }
export interface Report {
  kind: string; filename: string; sha256: string; size_bytes: number; encoding: string; total_rows: number; valid_rows: number;
  error_count: number; errors: RowError[]; mapping: Record<string, string>; ignored_columns: string[]; unstored_columns: string[];
  missing_required: string[]; warnings: string[]; stage_order: string[]; summary: Record<string, number | string | null>; ok: boolean;
}
export interface ServerResult { status: string; upload_id: string | null; imported: Record<string, number>; report: Report }
export interface UploadRow { id: string; kind: string; filename: string; status: string; total_rows: number; imported_rows: number; error_count: number; created_at: string }

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");


// ───────── Modo navegador (sem API): negócios do CSV -> painel ─────────
// Regras espelham src/omnidata/datasets/{coerce,validate}.py (padrões de ganho/perdido e ordem de etapas vêm do mesmo spec).
const S = spec as unknown as { stageRanks: [string, number][]; won: string; lost: string; statusWords: Record<string, string> };
const WON = new RegExp(S.won), LOST = new RegExp(S.lost);
export const classifyStage = (label: string): "open" | "won" | "lost" => { const n = norm(label); return WON.test(n) ? "won" : LOST.test(n) ? "lost" : "open"; };
export const stageRank = (label: string) => { const n = norm(label); for (const [p, r] of S.stageRanks) if (new RegExp(p).test(n)) return r; return 50; };

export function parseAmount(v: string): number | null {
  let s = v.replace(/r\$|us\$|\$|€|\s/gi, "");
  if (!s) return null;
  const neg = s.startsWith("-") || (s.startsWith("(") && s.endsWith(")"));
  s = s.replace(/^[-(]+|[)]+$/g, "");
  if (s.includes(",") && s.includes(".")) s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  else if (s.includes(",")) s = /^\d{1,3}(,\d{3})+$/.test(s) ? s.replace(/,/g, "") : s.replace(",", ".");
  else if (s.includes(".") && /^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
  const n = Number(s);
  if (!s || !Number.isFinite(n)) throw new Error(`valor numérico inválido: “${v}”`);
  if (neg || n < 0) throw new Error("valor negativo não é aceito");
  return n;
}

export function parseDate(v: string): Date | null {
  const t = v.trim();
  if (!t) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(t);
  const b = /^(\d{2})\/(\d{2})\/(\d{4})(?: (\d{2}):(\d{2}))?$/.exec(t);
  const parts: number[] | null = m ? [+m[1], +m[2], +m[3], +(m[4] ?? 0), +(m[5] ?? 0)] : b ? [+b[3], +b[2], +b[1], +(b[4] ?? 0), +(b[5] ?? 0)] : null;
  const bad = () => new Error(`data inválida: “${v}” (use AAAA-MM-DD ou DD/MM/AAAA)`);
  if (!parts) throw bad();
  const [y, mo, d, h, mi] = parts;
  const dt = new Date(y, mo - 1, d, h, mi);
  if (dt.getMonth() !== mo - 1 || dt.getDate() !== d) throw bad();
  return dt;
}

export interface BuiltDeals {
  deals: Deal[]; records: Rec[]; probs: Record<string, number>; stageOrder: string[]; total: number; skipped: number;
  errors: RowError[]; missing: string[]; ignored: string[]; lostWithReason: number;
}

export function buildDeals(text: string): BuiltDeals {
  const kind = KINDS.find((k) => k.key === "deals")!;
  const { headers, rows, total } = parseCsv(text, Infinity);
  const { mapping, ignored, missing } = mapHeaders(kind, headers);
  const out: BuiltDeals = { deals: [], records: [], probs: {}, stageOrder: [], total, skipped: 0, errors: [], missing, ignored, lostWithReason: 0 };
  if (missing.length) return out;
  const at = (r: string[], c: string) => (c in mapping ? (r[headers.indexOf(mapping[c])] ?? "").trim() : "");
  const seen = new Set<string>();
  const firstSeen: string[] = [];
  const now = Date.now();
  rows.forEach((r, i) => {
    const line = i + 2;
    const fail = (column: string, message: string) => { out.skipped++; if (out.errors.length < 200) out.errors.push({ line, column, message }); };
    const id = at(r, "id"), name = at(r, "name"), stage = at(r, "stage");
    if (!id || !name || !stage) return fail(mapping[!id ? "id" : !name ? "name" : "stage"], "campo obrigatório vazio");
    if (seen.has(id)) return fail(mapping.id, `id repetido: ${id}`);
    seen.add(id);
    let amount: number | null, close: Date | null, next: Date | null;
    try { amount = at(r, "amount") ? parseAmount(at(r, "amount")) : null; } catch (e) { return fail(mapping.amount, (e as Error).message); }
    try { close = parseDate(at(r, "close_date")); } catch (e) { return fail(mapping.close_date, (e as Error).message); }
    try { next = parseDate(at(r, "next_activity")); } catch (e) { return fail(mapping.next_activity, (e as Error).message); }
    const sw = S.statusWords[norm(at(r, "status"))];
    const status = (sw as "open" | "won" | "lost" | undefined) ?? classifyStage(stage);
    if (status !== "open" && !close) return fail(mapping.close_date ?? "close_date", "negócio fechado sem data de fechamento");
    let reason: string | null = at(r, "lost_reason") || null;
    if (status === "lost" && !reason)
      for (const seg of at(r, "notes").split(" | ")) { const m = /^\s*motivo (?:da|de) perda:\s*(.+?)\.?\s*$/i.exec(seg); if (m) { reason = m[1].trim(); break; } }
    if (status !== "lost") reason = null; else if (reason) out.lostWithReason++;
    if (status === "open" && !firstSeen.includes(stage)) firstSeen.push(stage);
    out.records.push({ id, name, status, amount: amount ?? 0, campaign: at(r, "campaign") || null, reason, notes: at(r, "notes").split(" | ").map((x) => x.trim()).filter(Boolean) });
    out.deals.push({ id, name, owner: at(r, "owner") || "Sem dono", stage, status, amount: amount ?? 0, daysInStage: 0, nextStep: !!next,
      quietDays: 0, overdue: status === "open" && !!close && close.getTime() < now, reason });
  });
  out.stageOrder = [...firstSeen].sort((a, b) => stageRank(a) - stageRank(b) || firstSeen.indexOf(a) - firstSeen.indexOf(b));
  const n = out.stageOrder.length;
  out.stageOrder.forEach((st, i) => { out.probs[st] = n > 1 ? Math.round((0.1 + (0.8 * i) / (n - 1)) * 1000) / 1000 : 0.4; });
  return out;
}
