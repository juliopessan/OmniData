"use client";
import Link from "next/link";
import { useMemo } from "react";
import { Eyebrow, Fig, Flag, Measured } from "./Ledger";
import { SourceBanner } from "./DashViews";
import { analyze, type Group } from "@/lib/insights";
import { brl, pct } from "@/lib/metrics";
import { TEAM } from "@/lib/team";
import { useStored } from "@/lib/upload-store";

const fmt = (n: number) => n.toLocaleString("pt-BR");
const p0 = (v: number | null) => (v === null ? "—" : pct(v, 0));

/** Quem cuida de cada insight: o cadastro da equipe vem do back-end (team.json). */
function AgentTag({ k }: { k: string }) {
  const m = TEAM.members.find((x) => x.key === k)!;
  return (
    <Link href="/dashboard/equipe" className="agent-tag" title={m.tagline}>
      <span className="mono-tile sm" aria-hidden="true">{m.name.slice(0, 2)}</span>
      <span><b>{m.name}</b> · {m.title}</span>
    </Link>
  );
}

const Mini = ({ v }: { v: number }) => <span className="minibar" aria-hidden="true"><i style={{ width: `${Math.round(v * 100)}%` }} /></span>;

function GroupTable({ rows, label, money = false }: { rows: Group[]; label: string; money?: boolean }) {
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => r.deals));
  return (
    <div className="tbl-wrap"><table>
      <thead><tr><th>{label}</th><th className="num">Negócios</th>{money && <th className="num">Em aberto</th>}<th className="num">Ganho</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.key}><td><b>{r.key}</b><Mini v={r.deals / max} /></td><td className="num">{fmt(r.deals)}</td>{money && <td className="num">{brl(r.openAmount)}</td>}
          <td className="num">{p0(r.winRate)}{r.lowN && r.winRate !== null ? " *" : ""}</td></tr>))}</tbody>
    </table></div>
  );
}

export function InsightsView() {
  const stored = useStored();
  const a = useMemo(() => (stored?.records?.length ? analyze(stored.records, 8) : null), [stored]);

  return (
    <>
      <div className="main-head"><div><Eyebrow>Insights de empresas</Eyebrow><h1 className="h2">O que as empresas dizem</h1></div></div>
      <SourceBanner />
      {!a && (
        <div className="rule-note"><span className="rule-k">Sem dados para analisar</span>
          <p>Os insights vêm das notas e dos nomes dos negócios. Envie um arquivo em <Link href="/dashboard/datasets" style={{ textDecoration: "underline" }}>Datasets</Link>{stored && !stored.records ? " (recarregue o seu: ele foi salvo antes deste recurso)" : ""} e volte aqui.</p></div>
      )}
      {a && stored && (
        <>
          <div className="ledger">
            <div className="ledger-head"><span className="live">Cobertura dos insights</span><span className="meta">{fmt(a.coverage.deals)} negócios</span></div>
            <div className="figs">
              <Fig value={p0(a.coverage.withNotes)} label="com notas" />
              <Fig value={p0(a.coverage.withPain)} label="com dor registrada" />
              <Fig value={p0(a.coverage.withSystem)} label="citam sistema" />
              <Fig value={p0(a.coverage.withDemand)} label="com tipo de demanda" />
              <Fig value={p0(a.coverage.withCampaign)} label="com campanha" />
              <Fig value={p0(a.coverage.lostWithReason)} label="perdas com motivo" />
            </div>
            <Measured k="Contado, não estimado">Cada número é uma contagem sobre “{stored.filename}”, feita no seu navegador com dicionários fixos (sem modelo de linguagem). Rankings mostram o que foi <b>anotado</b>, não o mercado todo.</Measured>
          </div>
          <div className="agent-row"><AgentTag k="argus" /><span className="note">cuida da confiança: onde a cobertura é baixa, o ranking é só indicativo</span></div>

          <section className="stack" style={{ gap: 12 }}>
            <div className="panel-t"><h2 className="h3">Dores</h2><AgentTag k="lyra" /></div>
            {a.pains.items.length ? (
              <div className="tbl-wrap"><table>
                <thead><tr><th>Dor registrada nas notas</th><th className="num">Negócios</th><th className="num">Parcela</th></tr></thead>
                <tbody>{a.pains.items.map((p) => <tr key={p.pain}><td><b>{p.pain}</b><Mini v={p.share / a.pains.items[0].share} /></td><td className="num">{fmt(p.deals)}</td><td className="num">{p0(p.share)}</td></tr>)}</tbody>
              </table></div>
            ) : <p className="note">Nenhuma nota traz “Dor validada: …” ou “Dor principal: …”.</p>}
            {a.pains.lowN && a.pains.items.length > 0 && <Flag k="Amostra pequena">Só {a.pains.withPain} negócios têm dor registrada (mínimo de 20 para um ranking confiável). Trate como indicativo.</Flag>}
          </section>

          <section className="stack" style={{ gap: 12 }}>
            <div className="panel-t"><h2 className="h3">Termos recorrentes</h2><AgentTag k="lyra" /></div>
            <div className="grid2">
              <div className="stack" style={{ gap: 6 }}><span className="rule-k">Palavras (negócios que citam)</span>
                <div className="tbl-wrap"><table><tbody>{a.terms.words.map((t) => <tr key={t.term}><td><b>{t.term}</b></td><td className="num">{fmt(t.deals)}</td></tr>)}</tbody></table></div></div>
              <div className="stack" style={{ gap: 6 }}><span className="rule-k">Frases · ganho entre fechados</span>
                <div className="tbl-wrap"><table><tbody>{a.terms.phrases.map((t) => <tr key={t.term}><td><b>{t.term}</b></td><td className="num">{fmt(t.deals)}</td><td className="num">{p0(t.winRate)}</td></tr>)}</tbody></table></div></div>
            </div>
            <div className="rule-note"><span className="rule-k">Leia com cuidado</span><p>Associação com ganho é correlação. Termos como “contrato assinado” ou “post-mortem” descrevem o resultado, não a causa.</p></div>
          </section>

          <section className="stack" style={{ gap: 12 }}>
            <div className="panel-t"><h2 className="h3">ERPs e sistemas</h2><AgentTag k="altair" /></div>
            <div className="grid2">
              {([["ERPs", a.systems.erp], ["CRM e vendas", a.systems.crm]] as const).map(([title, rows]) => (
                <div key={title} className="stack" style={{ gap: 6 }}><span className="rule-k">{title}</span>
                  {rows.length ? <div className="tbl-wrap"><table>
                    <thead><tr><th>Sistema</th><th className="num">Negócios</th><th className="num">Ganhamos contra</th></tr></thead>
                    <tbody>{rows.map((s) => <tr key={s.system}><td><b>{s.system}</b></td><td className="num">{fmt(s.deals)}</td><td className="num">{fmt(s.wonAgainst)}</td></tr>)}</tbody></table></div>
                    : <p className="note">Nenhum citado nas notas.</p>}
                </div>
              ))}
            </div>
          </section>

          <section className="stack" style={{ gap: 12 }}>
            <div className="panel-t"><h2 className="h3">Tipo de demanda</h2><AgentTag k="altair" /></div>
            <GroupTable rows={a.demand} label="O que compram (sufixo do nome do negócio)" money />
            <p className="note">Convenção: “Empresa – Demanda” ou “Cliente{"<>"}Parceiro [Demanda]”. Ganho marcado com * tem menos de 20 fechados.</p>
          </section>

          <section className="stack" style={{ gap: 12 }}>
            <div className="panel-t"><h2 className="h3">Outros insights</h2><AgentTag k="vega" /></div>
            {a.segments.length ? <GroupTable rows={a.segments} label="Segmento (inferido do nome da empresa)" /> : <p className="note">Nenhum segmento identificado: nenhuma palavra final dos nomes se repete em pelo menos 8 negócios.</p>}
            <GroupTable rows={a.campaigns} label="Campanha" />
            {a.lossTaxonomy.length > 0 && (
              <div className="tbl-wrap"><table>
                <thead><tr><th>Motivo de perda (taxonomia do PRD)</th><th className="num">Negócios</th></tr></thead>
                <tbody>{a.lossTaxonomy.map((t) => <tr key={t.code}><td><b>{t.label}</b><Mini v={t.deals / a.lossTaxonomy[0].deals} /></td><td className="num">{fmt(t.deals)}</td></tr>)}</tbody>
              </table></div>
            )}
          </section>

          <div className="agent-row"><AgentTag k="aurora" /><span className="note">
            insight do dia: {a.pains.items[0] && !a.pains.lowN ? `dor mais citada, ${a.pains.items[0].pain}` : `dores: só ${a.pains.withPain} negócio(s) com dor registrada, pouco para destacar`}{a.demand[0] ? `; demanda que mais aparece, ${a.demand[0].key}` : ""}{a.systems.all[0] ? `; sistema mais citado, ${a.systems.all[0].system}` : ""}.</span></div>
        </>
      )}
    </>
  );
}
