"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Eyebrow, Fig, Flag, Measured } from "./Ledger";
import { SourceBanner } from "./DashViews";
import { AgentTag } from "./AgentTag";
import { HBars, RangeBars, Ring, SplitBar } from "./charts";
import { analyze } from "@/lib/insights";
import { fixQueue } from "@/lib/hygiene";
import { decide, type Decision } from "@/lib/decisions";
import { forecast } from "@/lib/forecast";
import { brl, pct, statusOf } from "@/lib/metrics";
import { useStored } from "@/lib/upload-store";

const fmt = (n: number) => n.toLocaleString("pt-BR");
const short = (s: string, k = 40) => (s.length > k ? `${s.slice(0, k - 1)}…` : s);
const winNote = (closed: number, rate: number | null, low: boolean) => (closed ? `ganho ${pct(rate ?? 0, 0)} em ${closed} ${closed === 1 ? "fechado" : "fechados"}${low ? " (amostra pequena)" : ""}` : "sem negócios fechados: conversão n/d");

const num = (v: string) => { const n = Number(v.replace(/\./g, "").replace(",", ".")); return v.trim() && Number.isFinite(n) && n >= 0 ? n : null; };

/** Previsão estatística do pipeline aberto (camada 1). O modelo de ML está desligado até haver dados para ele. */
function ForecastSection({ openAmounts, wins, losses }: { openAmounts: number[]; wins: number; losses: number }) {
  const [quotaTxt, setQuotaTxt] = useState("");
  const [doneTxt, setDoneTxt] = useState("");
  const quota = num(quotaTxt), realized = num(doneTxt) ?? 0;
  const f = useMemo(() => forecast(openAmounts, wins, losses, realized, quota), [openAmounts, wins, losses, realized, quota]);
  const sc = f.scenarios;
  const rows = sc ? ([["low", "conservador"], ["mid", "central"], ["high", "otimista"]] as const).map(([k, name]) => ({
    label: `${name} (taxa ${pct(sc[k].p, 0)})`, lo: sc[k].p10, mid: sc[k].p50, hi: sc[k].p90, display: `${brl(sc[k].p10)} a ${brl(sc[k].p90)}` })) : [];
  const max = Math.max(1, ...rows.map((r) => r.hi), f.target ?? 0);
  return (
    <section className="meet-sec" id="previsao">
      <div className="panel-t"><h2 className="h3"><span className="mono">06</span> Previsão: o que o pipeline ainda pode render</h2><AgentTag k="vega" /></div>
      <div className="fc-inputs no-print">
        <label>Meta do período (R$)<input inputMode="decimal" value={quotaTxt} onChange={(e) => setQuotaTxt(e.target.value)} placeholder="ex.: 500000" /></label>
        <label>Já ganho no período (R$)<input inputMode="decimal" value={doneTxt} onChange={(e) => setDoneTxt(e.target.value)} placeholder="ex.: 120000" /></label>
      </div>
      {quota !== null && <p className="note print-only">Meta informada: {brl(quota)} · já ganho: {brl(realized)}</p>}
      {f.status === "insufficient" && <Flag k="Sem base para prever">Só {fmt(f.closed)} negócios fechados (o mínimo é 10). Com tão pouco histórico, qualquer porcentagem seria chute.</Flag>}
      {f.status === "no_pipeline" && <p className="note">Não há negócios abertos com valor para prever. Preencha o valor dos abertos (veja a seção 05).</p>}
      {sc && f.winRate !== undefined && f.winRateCi && (
        <>
          <div className="figs" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
            <Fig value={pct(f.winRate, 0)} label={`taxa de ganho (${fmt(f.wins)} de ${fmt(f.closed)} fechados; ${pct(f.winRateCi[0], 0)} a ${pct(f.winRateCi[1], 0)})`} />
            <Fig value={brl(sc.mid.expected)} label={`esperado dos ${fmt(f.openWithValue)} abertos com valor (${brl(f.openAmount)})`} />
            {quota !== null && f.target !== null && f.target !== undefined ? <Fig value={f.target <= 0 ? "meta batida" : `${f.backlog ? "até " : ""}${pct(sc.mid.probTarget ?? 0, 0)}`} label={f.target <= 0 ? "já ganho cobre a meta" : `${f.backlog ? "teto da chance" : "chance"} de bater a meta (${pct(sc.low.probTarget ?? 0, 0)} a ${pct(sc.high.probTarget ?? 0, 0)})`} /> : <Fig value="n/d" label="chance de bater a meta: informe a meta" />}
          </div>
          <RangeBars label="Faixa provável do que o pipeline aberto rende (10% a 90%)" rows={rows} max={max} target={f.target ?? null} />
          <p className="note">A barra vai do pior ao melhor resultado provável (10% a 90%); o traço claro é a mediana{f.target ? " e a linha tracejada é o que falta para a meta" : ""}. Os três cenários usam a taxa de ganho baixa, central e alta do intervalo de confiança.</p>
          {f.backlog && <Flag k="Trate como teto, não como previsão">Há {fmt(f.openWithValue)} negócios abertos com valor para só {fmt(f.closed)} fechados. A taxa de ganho do passado não descreve esse acúmulo (a maioria pode nunca fechar).</Flag>}
          {!f.backlog && f.status === "indicative" && <p className="note">Menos de 20 fechados: resultado só indicativo.</p>}
        </>
      )}
      <p className="note">A taxa vem só dos negócios fechados e tende a ser otimista: negócios parados não entram como perdidos. Modelo de ML (scikit-learn): desligado. Faltam {f.closed < 300 ? `pelo menos 300 fechados (há ${fmt(f.closed)}), ` : ""}data de criação e histórico de etapas, para usar só o que existia antes do fechamento.</p>
    </section>
  );
}

function DecisionCard({ d }: { d: Decision }) {
  return (
    <article className="decision">
      <span className="decision-k">Sugestão {d.priority}</span>
      <h3 className="h3">{d.title}</h3>
      <p className="rule">Regra: {d.rule}</p>
      <ul aria-label="Números que sustentam a sugestão">{d.evidence.map((e) => <li key={e}>{e}</li>)}</ul>
      <p className="act">{d.action}</p>
      {d.caution && <p className="note">Cuidado: {d.caution}</p>}
      <AgentTag k={d.agent} />
    </article>
  );
}

export function ReuniaoView() {
  const stored = useStored();
  const ready = !!stored?.records?.length;
  const view = useMemo(() => {
    if (!stored?.records?.length) return null;
    const a = analyze(stored.records, 8);
    const q = fixQueue(stored.deals, stored.records, 6);
    const open = stored.deals.filter((d) => statusOf(d) === "open");
    const amount = open.reduce((s, d) => s + d.amount, 0);
    const withValue = open.filter((d) => d.amount > 0);
    const top = [...withValue].sort((x, y) => y.amount - x.amount);
    return { a, q, open, amount, withValue: withValue.length, top, decisions: decide(stored.deals, a, q), amounts: open.map((d) => d.amount),
      wins: stored.deals.filter((d) => statusOf(d) === "won").length, losses: stored.deals.filter((d) => statusOf(d) === "lost").length };
  }, [stored]);

  const print = () => window.print();
  const full = () => { try { void document.documentElement.requestFullscreen?.(); } catch { /* o navegador pode negar */ } };

  return (
    <>
      <div className="main-head">
        <div><Eyebrow>Reunião de vendas</Eyebrow><h1 className="h2">KPIs e decisões da semana</h1></div>
        <div className="meet-tools no-print">
          <button type="button" className="btn ghost" onClick={full}>Tela cheia</button>
          <button type="button" className="btn" onClick={print} disabled={!view}>Imprimir / salvar PDF</button>
        </div>
      </div>
      <SourceBanner />
      {!ready && (
        <div className="rule-note"><span className="rule-k">Sem dados para a reunião</span>
          <p>O Modo reunião usa os negócios e as notas do seu arquivo. Envie o export em <Link href="/dashboard/datasets" style={{ textDecoration: "underline" }}>Datasets</Link>{stored && !stored.records ? " (recarregue o seu: ele foi salvo antes dos Insights)" : ""} e volte aqui.</p></div>
      )}
      {view && stored && (
        <>
          <div className="ledger">
            <div className="ledger-head"><span className="live">Números da reunião</span><span className="meta">{fmt(stored.deals.length)} negócios · {stored.filename}</span></div>
            <div className="figs">
              <Fig value={fmt(view.open.length)} label="negócios abertos" />
              <Fig value={brl(view.amount)} label="pipeline aberto" />
              <Fig value={`${fmt(view.withValue)} de ${fmt(view.open.length)}`} label="abertos com valor" />
              <Fig value={view.top[0] && view.amount ? pct(view.top[0].amount / view.amount, 0) : "n/d"} label="no maior negócio" />
            </div>
            <Measured k="Contado, não estimado">Cada número vem de uma contagem sobre o arquivo, feita no navegador. As <b>decisões</b> no fim são sugestões geradas por regras fixas, e cada uma mostra a regra e a evidência.</Measured>
          </div>
          <nav className="no-print note" aria-label="Seções da reunião">
            <a href="#pipeline">01 Pipeline</a> · <a href="#demanda">02 Demanda</a> · <a href="#erp">03 ERPs</a> · <a href="#dores">04 Dores e termos</a> · <a href="#qualidade">05 Qualidade</a> · <a href="#previsao">06 Previsão</a> · <a href="#decisoes">Decisões</a>
          </nav>

          <section className="meet-sec" id="pipeline">
            <div className="panel-t"><h2 className="h3"><span className="mono">01</span> Pipeline: quanto e onde</h2><AgentTag k="altair" /></div>
            <SplitBar done={view.withValue} gap={view.open.length - view.withValue} doneLabel="com valor" gapLabel="sem valor" />
            {view.top.length > 0 && <HBars label="Maiores negócios abertos" rows={view.top.slice(0, 6).map((d) => ({ label: short(d.name), value: d.amount, display: view.amount ? `${brl(d.amount)} · ${pct(d.amount / view.amount, 0)}` : brl(d.amount) }))} />}
          </section>

          <section className="meet-sec" id="demanda">
            <div className="panel-t"><h2 className="h3"><span className="mono">02</span> Demanda: o que compram</h2><AgentTag k="altair" /></div>
            {view.a.demand.length ? <HBars label="Negócios por tipo de demanda" rows={view.a.demand.map((g) => ({ label: g.key, value: g.deals, display: fmt(g.deals), note: winNote(g.closed, g.winRate, g.lowN) }))} />
              : <p className="note">Nenhum tipo de demanda identificado nos nomes dos negócios.</p>}
          </section>

          <section className="meet-sec" id="erp">
            <div className="panel-t"><h2 className="h3"><span className="mono">03</span> ERPs citados nas contas</h2><AgentTag k="altair" /></div>
            {view.a.systems.erp.length ? <HBars label="Negócios por ERP" rows={view.a.systems.erp.map((s) => ({ label: s.system, value: s.deals, display: fmt(s.deals) }))} />
              : <p className="note">Nenhum ERP citado nas notas.</p>}
            <p className="note">Conta o que foi anotado, não o mercado todo.</p>
          </section>

          <section className="meet-sec" id="dores">
            <div className="panel-t"><h2 className="h3"><span className="mono">04</span> Dores e termos recorrentes</h2><AgentTag k="lyra" /></div>
            {view.a.pains.lowN
              ? <Flag k="Amostra pequena">Só {fmt(view.a.pains.withPain)} de {fmt(view.a.coverage.deals)} negócios têm dor registrada (o mínimo para um ranking é 20). Não use este bloco para decidir.</Flag>
              : <HBars label="Dores mais citadas" rows={view.a.pains.items.map((p) => ({ label: short(p.pain, 60), value: p.deals, display: fmt(p.deals) }))} />}
            {view.a.terms.phrases.length > 0 && <HBars label="Frases mais repetidas nas notas" rows={view.a.terms.phrases.slice(0, 6).map((t) => ({ label: t.term, value: t.deals, display: fmt(t.deals) }))} />}
            <p className="note">Frases como “aguardando retorno” descrevem o andamento, não a dor; associação com ganho é correlação, nunca causa.</p>
          </section>

          <section className="meet-sec" id="qualidade">
            <div className="panel-t"><h2 className="h3"><span className="mono">05</span> Qualidade: o que corrigir</h2><AgentTag k="polaris" /></div>
            <div className="rings">
              <Ring value={view.a.coverage.withNotes} label="com notas" />
              <Ring value={view.a.coverage.withPain} label="com dor" />
              <Ring value={view.a.coverage.withSystem} label="citam sistema" />
              <Ring value={view.a.coverage.withDemand} label="com demanda" />
              <Ring value={view.a.coverage.lostWithReason} label="perdas c/ motivo" />
            </div>
            <HBars gap label="Lacunas nos negócios abertos" rows={view.q.issues.map((i) => ({ label: i.label, value: i.deals, display: fmt(i.deals), note: i.systemic ? "quase todos: confira a origem do dado antes de cobrar" : i.who === "manager" ? "resolve o gestor" : undefined }))} />
          </section>

          <ForecastSection openAmounts={view.amounts} wins={view.wins} losses={view.losses} />

          <section className="meet-sec" id="decisoes">
            <div className="panel-t"><h2 className="h3">O que o time precisa <span className="voice">decidir</span></h2></div>
            {view.decisions.length === 0
              ? <p className="note">Nenhuma regra disparou com os dados atuais.</p>
              : <>
                  <div className="stack decisions-list" style={{ gap: 14 }}>{view.decisions.slice(0, 5).map((d) => <DecisionCard key={d.id} d={d} />)}</div>
                  {view.decisions.length > 5 && (
                    <>
                      <details className="no-print"><summary className="note">Ver as outras {view.decisions.length - 5} sugestões</summary>
                        <div className="stack" style={{ gap: 14, marginTop: 14 }}>{view.decisions.slice(5).map((d) => <DecisionCard key={d.id} d={d} />)}</div>
                      </details>
                      <div className="print-only decisions-list">{view.decisions.slice(5).map((d) => <DecisionCard key={d.id} d={d} />)}</div>
                    </>
                  )}
                </>}
          </section>
        </>
      )}
    </>
  );
}
