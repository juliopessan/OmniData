"use client";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { API_URL, KINDS, buildDeals, mapHeaders, parseCsv, type BuiltDeals, type Report, type ServerResult, type UploadRow } from "@/lib/datasets";
import { clearStored, saveStored, useStored } from "@/lib/upload-store";
import { Bar, Fig, Flag, Measured } from "./Ledger";

type Preview = { headers: string[]; rows: string[][]; total: number; delimiter: string } | null;
const fmt = (n: number) => n.toLocaleString("pt-BR");

export function DatasetUploader() {
  const [kindKey, setKindKey] = useState("deals");
  const kind = KINDS.find((k) => k.key === kindKey)!;
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview>(null);
  const [drag, setDrag] = useState(false);
  const [api, setApi] = useState(API_URL);
  const [token, setToken] = useState("");
  const [allowPartial, setAllowPartial] = useState(false);
  const [replace, setReplace] = useState(false);
  const [importNotes, setImportNotes] = useState(true);
  const [stageOrder, setStageOrder] = useState("");
  const [busy, setBusy] = useState<"" | "validate" | "import">("");
  const [result, setResult] = useState<ServerResult | null>(null);
  const [validatedKey, setValidatedKey] = useState("");
  const [error, setError] = useState("");
  const [history, setHistory] = useState<UploadRow[] | null>(null);
  const [built, setBuilt] = useState<BuiltDeals | null>(null);
  const [savedMsg, setSavedMsg] = useState("");
  const stored = useStored();
  const input = useRef<HTMLInputElement>(null);

  const key = (f: File | null) => (f ? `${f.name}:${f.size}:${f.lastModified}:${kindKey}:${allowPartial}:${replace}:${importNotes}:${stageOrder}` : "");

  const load = useCallback(async (f: File) => {
    setFile(f); setResult(null); setError(""); setValidatedKey(""); setBuilt(null); setSavedMsg("");
    if (/\.xlsx$/i.test(f.name)) { setPreview(null); return; } // planilhas: só o servidor lê
    if (f.size > 10_000_000) { setError("Arquivo acima de 10 MB."); return; }
    const text = await f.text();
    setPreview(parseCsv(text));
    setBuilt(buildDeals(text));
  }, []);

  const useSample = async () => {
    const r = await fetch("/samples/hubspot_deals_sintetico_amostra.csv");
    setKindKey("deals");
    await load(new File([await r.blob()], "hubspot_deals_sintetico_amostra.csv", { type: "text/csv" }));
  };

  const call = async (dry: boolean) => {
    if (!file) return;
    setBusy(dry ? "validate" : "import"); setError("");
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("dry_run", String(dry)); fd.append("allow_partial", String(allowPartial));
      fd.append("replace", String(replace)); fd.append("import_notes", String(importNotes));
      if (stageOrder.trim()) fd.append("stage_order", stageOrder);
      const r = await fetch(`${api.replace(/\/$/, "")}/api/datasets/${kindKey}`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd });
      const j = await r.json().catch(() => ({}));
      if (r.status === 401) throw new Error("Token inválido.");
      if (r.status === 503) throw new Error("Upload desativado no servidor (ADMIN_API_TOKEN não configurado).");
      if (j.code) throw new Error(j.message ?? "Arquivo recusado.");
      if (!j.report) throw new Error(`Erro ${r.status} no servidor.`);
      setResult(j as ServerResult);
      if (dry && j.report.ok) setValidatedKey(key(file));
      if (!dry) refreshHistory();
    } catch (e) {
      setError(e instanceof TypeError ? "Não consegui falar com a API (URL, rede ou CORS)." : (e as Error).message);
    } finally { setBusy(""); }
  };

  const refreshHistory = async () => {
    try {
      const r = await fetch(`${api.replace(/\/$/, "")}/api/datasets`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.ok) setHistory(await r.json());
    } catch { /* histórico é opcional */ }
  };

  const doImport = () => {
    const warn = replace ? "\n\nATENÇÃO: “substituir” apaga tudo o que foi importado antes por upload." : "";
    if (window.confirm(`Importar ${result?.report.valid_rows ?? 0} linhas de “${file?.name}” para o banco?${warn}`)) call(false);
  };

  const local = preview ? mapHeaders(kind, preview.headers) : null;
  const canValidate = !!file && !!api && !!token && !busy;
  const canImport = canValidate && validatedKey === key(file) && result?.status === "validated";

  return (
    <div className="stack" style={{ gap: 28 }}>
      {!API_URL && (
        <div className="rule-note"><span className="rule-k">Modo demonstração</span>
          <p>Este site não tem API configurada (<code>NEXT_PUBLIC_API_URL</code>). A prévia local funciona; para validar e importar de verdade, informe a URL da API e o token abaixo ou use <code>omnidata dataset import</code>.</p></div>
      )}

      <div className="stack" style={{ gap: 12 }}>
        <div className="chips" role="group" aria-label="Tipo de dataset">
          {KINDS.map((k) => <button key={k.key} className="chip" aria-pressed={k.key === kindKey} onClick={() => { setKindKey(k.key); setResult(null); setValidatedKey(""); }}>{k.title}</button>)}
        </div>
        <p className="body">{kind.description}</p>
        <p className="note">
          Modelo: <a href={`/templates/omnidata-${kindKey}-modelo.csv`} download style={{ textDecoration: "underline" }}>baixar CSV</a>
          {kindKey === "deals" && <> · <button className="linkbtn" onClick={useSample}>usar exemplo (exportação do HubSpot, 63 linhas)</button></>}
        </p>
      </div>

      <div className={`dropzone${drag ? " on" : ""}`} role="button" tabIndex={0} aria-label="Escolher arquivo"
        onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) load(f); }}>
        <input ref={input} type="file" accept=".csv,.tsv,.txt,.xlsx" hidden onChange={(e) => e.target.files?.[0] && load(e.target.files[0])} />
        {file ? <><b>{file.name}</b><span className="note">{(file.size / 1024).toFixed(0)} KB · clique ou solte outro arquivo para trocar</span></>
              : <><b>Solte um arquivo aqui</b><span className="note">CSV ou XLSX · até 10 MB · UTF-8 ou Windows-1252</span></>}
      </div>

      {file && !preview && <p className="note">Prévia local indisponível para planilhas .xlsx: a leitura e a validação acontecem no servidor.</p>}
      {local && preview && (
        <section className="stack" style={{ gap: 12 }}>
          <div className="panel-t"><h2 className="h3">Prévia local</h2><span className="tag">{fmt(preview.total)} linhas · delimitador “{preview.delimiter === "\t" ? "tab" : preview.delimiter}”</span></div>
          <div className="tbl-wrap"><table>
            <thead><tr><th>Coluna do OmniData</th><th>Sua coluna</th><th>Situação</th></tr></thead>
            <tbody>
              {kind.columns.map((c) => (
                <tr key={c.name}><td><b>{c.name}</b>{c.hint && <span className="sub">{c.hint}</span>}</td>
                  <td>{local.mapping[c.name] ?? "—"}</td>
                  <td>{c.name in local.mapping ? <span className="tag">{c.stored ? "reconhecida" : "não importada"}</span> : c.required ? <span className="tag gap">obrigatória: falta</span> : <span className="tag">opcional</span>}</td></tr>
              ))}
            </tbody></table></div>
          {local.ignored.length > 0 && <p className="note">Colunas desconhecidas, nunca importadas: {local.ignored.join(", ")}.</p>}
          <div className="tbl-wrap"><table>
            <thead><tr>{preview.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
            <tbody>{preview.rows.slice(0, 5).map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c.slice(0, 60)}</td>)}</tr>)}</tbody></table></div>
        </section>
      )}

      {stored && (
        <div className="rule-note"><span className="rule-k">Painel usando seu arquivo</span>
          <p>“{stored.filename}” ({stored.deals.length.toLocaleString("pt-BR")} negócios) está ativo em Visão geral, Negócios e Qualidade, só neste navegador.{" "}
            <Link href="/dashboard" style={{ textDecoration: "underline" }}>Ver visão geral</Link> · <button className="linkbtn" onClick={clearStored}>remover</button></p></div>
      )}

      {file && kindKey === "deals" && built && !built.missing.length && (
        <section className="stack" style={{ gap: 12 }}>
          <div className="panel-t"><h2 className="h3">Usar no painel (neste navegador)</h2><span className="tag">sem servidor</span></div>
          <p className="body">Carrega os negócios do arquivo direto no painel, sem API e sem banco. Fica salvo só neste navegador; para gravar no banco de verdade, use o envio ao servidor abaixo.</p>
          <p className="note">
            {built.deals.length.toLocaleString("pt-BR")} negócios válidos de {built.total.toLocaleString("pt-BR")}
            {" · "}{built.deals.filter((d) => d.status === "open").length} abertos · {built.deals.filter((d) => d.status === "won").length} ganhos · {built.deals.filter((d) => d.status === "lost").length} perdidos
            {" · "}{built.lostWithReason} perdas com motivo{built.stageOrder.length ? ` · funil: ${built.stageOrder.join(" → ")}` : ""}
          </p>
          {built.skipped > 0 && (
            <Flag k={`${built.skipped} linha(s) puladas`}>
              Não entram no painel. Primeiras: {built.errors.slice(0, 4).map((e) => `linha ${e.line} (${e.column}): ${e.message}`).join(" · ")}.
            </Flag>
          )}
          <div className="actions">
            <button className="btn" disabled={!built.deals.length} onClick={() => {
              const ok = saveStored({ filename: file.name, savedAt: new Date().toISOString(), deals: built.deals, records: built.records, probs: built.probs, stageOrder: built.stageOrder });
              setSavedMsg(ok ? "ok" : "falhou");
            }}>Carregar no painel</button>
            {savedMsg === "ok" && <Link href="/dashboard" className="btn ghost">Abrir visão geral →</Link>}
            {savedMsg === "ok" && <Link href="/dashboard/insights" className="btn ghost">Ver insights →</Link>}
          </div>
          {savedMsg === "falhou" && <Flag k="Não consegui salvar">O navegador recusou o armazenamento (arquivo grande demais ou modo privado). Tente um arquivo menor.</Flag>}
        </section>
      )}
      {file && kindKey !== "deals" && <p className="note">No modo sem servidor só os negócios alimentam o painel. Metas exigem o envio ao servidor.</p>}

      {file && (
        <section className="stack" style={{ gap: 16 }}>
          <div className="panel-t"><h2 className="h3">Enviar para o servidor</h2></div>
          <div className="grid2" style={{ gap: 16 }}>
            <div className="field"><label htmlFor="api">URL da API</label><input id="api" value={api} onChange={(e) => setApi(e.target.value)} placeholder="https://api.suaempresa.com" /></div>
            <div className="field"><label htmlFor="tok">Token de admin</label><input id="tok" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="ADMIN_API_TOKEN (só fica na memória)" /></div>
          </div>
          <div className="opts">
            <label><input type="checkbox" checked={allowPartial} onChange={(e) => setAllowPartial(e.target.checked)} /> importar as linhas válidas mesmo com erros</label>
            {kindKey === "deals" && <>
              <label><input type="checkbox" checked={importNotes} onChange={(e) => setImportNotes(e.target.checked)} /> importar o texto das notas</label>
              <label><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> substituir importações anteriores</label>
              <div className="field"><label htmlFor="so">Ordem das etapas abertas (opcional)</label><input id="so" value={stageOrder} onChange={(e) => setStageOrder(e.target.value)} placeholder="Qualificação, Proposta enviada, Negociação" /></div></>}
          </div>
          {(!api || !token) && <p className="note">Os botões abaixo precisam da URL da API e do token (a API precisa estar no ar). Sem servidor, use “Carregar no painel” acima.</p>}
          <div className="actions">
            <button className="btn ghost" disabled={!canValidate} title={canValidate ? "" : "Informe a URL da API e o token"} onClick={() => call(true)}>{busy === "validate" ? "Validando…" : "Validar no servidor"}</button>
            <button className="btn" disabled={!canImport} onClick={doImport} title={canImport ? "" : "Valide primeiro, sem erros"}>{busy === "import" ? "Importando…" : "Importar"}</button>
          </div>
          {error && <Flag k="Não foi possível concluir">{error}</Flag>}
        </section>
      )}

      {result && <ReportView res={result} />}

      {token && api && (
        <section className="stack" style={{ gap: 12 }}>
          <div className="panel-t"><h2 className="h3">Histórico de uploads</h2><button className="linkbtn" onClick={refreshHistory}>atualizar</button></div>
          {history ? (
            <div className="tbl-wrap"><table>
              <thead><tr><th>Arquivo</th><th>Tipo</th><th>Status</th><th className="num">Linhas</th><th className="num">Importadas</th><th className="num">Erros</th></tr></thead>
              <tbody>{history.map((h) => <tr key={h.id}><td>{h.filename}<span className="sub mono">{new Date(h.created_at).toLocaleString("pt-BR")}</span></td><td>{h.kind}</td>
                <td><span className={`tag${h.status === "imported" ? "" : " gap"}`}>{h.status}</span></td><td className="num">{fmt(h.total_rows)}</td><td className="num">{fmt(h.imported_rows)}</td><td className="num">{fmt(h.error_count)}</td></tr>)}</tbody></table></div>
          ) : <p className="note">Clique em “atualizar” para carregar.</p>}
        </section>
      )}
    </div>
  );
}

function ReportView({ res }: { res: ServerResult }) {
  const r: Report = res.report;
  const s = r.summary;
  const imported = res.status === "imported";
  return (
    <section className="stack" style={{ gap: 20 }}>
      <div className="ledger">
        <div className="ledger-head"><span className="live">{imported ? "Importado" : "Validação no servidor"} · {r.kind}</span><span className="meta">{r.encoding}</span></div>
        <Bar label="Linhas no arquivo" value={fmt(r.total_rows)} width={1} tone="dim" />
        <Bar label="Linhas válidas" value={fmt(r.valid_rows)} width={r.total_rows ? r.valid_rows / r.total_rows : 0} tone="mint" />
        <div className="figs">
          <Fig value={fmt(r.error_count)} label="erros" />
          {"open" in s && <Fig value={fmt(Number(s.open))} label="abertos" />}
          {"won" in s && <Fig value={fmt(Number(s.won))} label="ganhos" />}
          {"lost" in s && <Fig value={fmt(Number(s.lost))} label="perdidos" />}
          {"owners" in s && <Fig value={fmt(Number(s.owners))} label="vendedores" />}
          {typeof s.lost_reason_coverage === "number" && <Fig value={`${Math.round(s.lost_reason_coverage * 100)}%`} label="perdas com motivo" />}
        </div>
        <Measured k={imported ? "Gravado" : "Nada foi gravado"}>
          Contado pelo servidor a partir do arquivo (SHA-256 <code>{r.sha256.slice(0, 12)}…</code>).
          {imported ? ` ${Object.entries(res.imported).map(([k, v]) => `${fmt(v)} ${k}`).join(", ")}.` : " Isto é uma validação: use “Importar” para gravar."}
        </Measured>
      </div>

      {r.missing_required.length > 0 && <Flag k="Colunas obrigatórias ausentes">Faltam: {r.missing_required.join(", ")}. Renomeie as colunas do arquivo (ou use o modelo) e envie de novo.</Flag>}
      {r.error_count > 0 && (
        <Flag k={`${fmt(r.error_count)} linha(s) com erro`}>
          Corrija no arquivo e envie de novo, ou marque “importar as linhas válidas”. Primeiros erros:
          <span className="tbl-wrap" style={{ display: "block", marginTop: 8 }}><table><tbody>
            {r.errors.slice(0, 15).map((e, i) => <tr key={i}><td className="num">linha {e.line}</td><td>{e.column}</td><td>{e.message}</td></tr>)}
          </tbody></table></span>
        </Flag>
      )}
      {r.warnings.length > 0 && <div className="rule-note"><span className="rule-k">Avisos</span>{r.warnings.map((w, i) => <p key={i}>{w}</p>)}</div>}
      {r.stage_order.length > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          <span className="rule-k">Ordem do funil usada (do início ao fim)</span>
          <ol className="day">{r.stage_order.map((st, i) => <li key={st}><time>{String(i + 1).padStart(2, "0")}</time><div><b>{st}</b></div></li>)}</ol>
        </div>
      )}
      {r.ignored_columns.length > 0 && <p className="note">Colunas ignoradas (desconhecidas, nunca importadas): {r.ignored_columns.join(", ")}.</p>}
      {r.unstored_columns.length > 0 && <p className="note">Reconhecidas mas não importadas de propósito: {r.unstored_columns.join(", ")}.</p>}
    </section>
  );
}
