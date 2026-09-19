"use client";
import { useMemo, useSyncExternalStore } from "react";
import { computeMetrics, computeMetricsFor, type Ctx } from "./metrics";
import type { Deal } from "./seed";

/** Dados enviados na página de datasets, guardados SÓ neste navegador (localStorage). Nada vai para servidor nenhum. */
const KEY = "omnidata:upload:deals:v1";
const EVT = "omnidata:upload";
export interface Stored { filename: string; savedAt: string; deals: Deal[]; probs: Record<string, number>; stageOrder: string[] }

let lastRaw: string | null = null, lastVal: Stored | null = null;
function read(): Stored | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw === lastRaw) return lastVal; // mesmo texto => mesma referência (exigência do useSyncExternalStore)
    lastRaw = raw; lastVal = raw ? (JSON.parse(raw) as Stored) : null;
  } catch { lastRaw = null; lastVal = null; }
  return lastVal;
}
const subscribe = (cb: () => void) => { window.addEventListener(EVT, cb); window.addEventListener("storage", cb); return () => { window.removeEventListener(EVT, cb); window.removeEventListener("storage", cb); }; };

export function saveStored(s: Stored): boolean {
  try { window.localStorage.setItem(KEY, JSON.stringify(s)); window.dispatchEvent(new Event(EVT)); return true; } catch { return false; } // cota cheia / bloqueado
}
export function clearStored() { try { window.localStorage.removeItem(KEY); } catch { /* ignora */ } window.dispatchEvent(new Event(EVT)); }
export const useStored = () => useSyncExternalStore(subscribe, read, () => null);

/** Métricas do painel: do arquivo enviado, se houver; senão, dos dados de exemplo. */
export function useDashboardData() {
  const stored = useStored();
  const m = useMemo(() => {
    if (!stored) return computeMetrics();
    const ctx: Ctx = { prob: stored.probs, p75: {}, quota: 0, hasTiming: false };
    return computeMetricsFor(stored.deals, ctx);
  }, [stored]);
  return { m, stored, source: stored ? ("upload" as const) : ("seed" as const) };
}
