"use client";
import Link from "next/link";
import { useMemo } from "react";
import { Eyebrow, Fig, Flag, Measured } from "./Ledger";
import { SourceBanner } from "./DashViews";
import { AgentTag } from "./AgentTag";
import { HBars, Ring, SplitBar } from "./charts";
import { analyze } from "@/lib/insights";
import { fixQueue } from "@/lib/hygiene";
import { decide, type Decision } from "@/lib/decisions";
import { brl, pct, statusOf } from "@/lib/metrics";
import { useStored } from "@/lib/upload-store";

const fmt = (n: number) => n.toLocaleString("pt-BR");
const short = (s: string, k = 40) => (s.length > k ? `${s.slice(0, k - 1)}…` : s);
const winNote = (closed: number, rate: number | null, low: boolean) => (closed ? `ganho ${pct(rate ?? 0, 0)} em ${closed} ${closed === 1 ? "fechado" : "fechados"}${low ? " (amostra pequena)" : ""}` : "sem negócios fechados: conversão n/d");

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
    return { a, q, open, amount, withValue: withValue.length, top, decisions: decide(stored.deals, a, q) };
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
            <a href="#pipeline">01 Pipeline</a> · <a href="#demanda">02 Demanda</a> · <a href="#erp">03 ERPs</a> · <a href="#dores">04 Dores e termos</a> · <a href="#qualidade">05 Qualidade</a> · <a href="#decisoes">Decisões</a>
          </nav>

          <section className="meet-sec" id="pipeline">
            <div className="panel-t"><h2 className="h3"><span className="mono">01</span> Pipeline: quanto e onde</h2><AgentTag k="altair" /></div>
            <SplitBar done={view.withValue} gap={view.open.length - view.withValue} doneLabel="com valor" gapLabel="sem valor" />
            {view.top.length > 0 && <HBars label="Maiores negócios abertos" rows={view.top.slice(0, 6).map((d) => ({ label: short(d.name), value: d.amount, display: brl(d.amount), note: view.amount ? `${pct(d.amount / view.amount, 0)} do pipeline` : undefined }))} />}
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

          <section className="meet-sec" id="decisoes">
            <div className="panel-t"><h2 className="h3">O que o time precisa <span className="voice">decidir</span></h2></div>
            {view.decisions.length === 0
              ? <p className="note">Nenhuma regra disparou com os dados atuais.</p>
              : <>
                  <div className="stack" style={{ gap: 14 }}>{view.decisions.slice(0, 5).map((d) => <DecisionCard key={d.id} d={d} />)}</div>
                  {view.decisions.length > 5 && (
                    <details className="no-print"><summary className="note">Ver as outras {view.decisions.length - 5} sugestões</summary>
                      <div className="stack" style={{ gap: 14, marginTop: 14 }}>{view.decisions.slice(5).map((d) => <DecisionCard key={d.id} d={d} />)}</div>
                    </details>
                  )}
                </>}
          </section>
        </>
      )}
    </>
  );
}
