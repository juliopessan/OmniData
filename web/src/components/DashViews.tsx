"use client";
import Link from "next/link";
import { Bar, Eyebrow, Fig, Flag, Measured } from "./Ledger";
import { SpinVerb } from "./SpinVerb";
import { brl, pad2, pct } from "@/lib/metrics";
import { useMemo } from "react";
import { AgentTag } from "./AgentTag";
import { fixQueue } from "@/lib/hygiene";
import { clearStored, useDashboardData, useStored } from "@/lib/upload-store";
import { MIN_N_RANKING, PERIOD, deals as SEED_DEALS } from "@/lib/seed";

/** Diz de onde vêm os números: exemplo sintético ou o arquivo enviado (só neste navegador). */
export function SourceBanner() {
  const { stored, source } = useDashboardData();
  if (source === "seed" || !stored)
    return (
      <div className="rule-note"><span className="rule-k">Dados de exemplo</span>
        <p>Estes números são sintéticos. Envie um arquivo em <Link href="/dashboard/datasets" style={{ textDecoration: "underline" }}>Datasets</Link> e o painel passa a usar os seus negócios.</p></div>
    );
  return (
    <div className="rule-note"><span className="rule-k">Seu arquivo</span>
      <p>Exibindo “{stored.filename}” · {stored.deals.length.toLocaleString("pt-BR")} negócios · salvo só neste navegador (nada foi enviado a servidor). Sem datas de criação e de etapa, “parado na etapa” não é calculado.{" "}
        <button className="linkbtn" onClick={clearStored}>voltar aos dados de exemplo</button></p></div>
  );
}

export function OverviewView() {
  const { m, stored, source } = useDashboardData();
  const upload = source === "upload";
  return (
    <>
      <div className="main-head">
        <div><Eyebrow>Visão geral · {upload ? "seu arquivo" : PERIOD}</Eyebrow><h1 className="h2">Resultado do time</h1></div>
        <SpinVerb verbs={["Sincronizando HubSpot", "Reconciliando", "Auditando"]} />
      </div>
      <SourceBanner />

      <div className="ledger">
        <div className="ledger-head"><span className="live">Números do time</span><span className="meta">{m.owners} vendedores · {upload ? "seu arquivo" : "dados sintéticos"}</span></div>
        {m.hasQuota ? (
          <>
            <Bar label="Meta do time" value={brl(m.quota)} width={1} tone="dim" />
            <Bar label="Ganho no período" value={brl(m.wonAmount)} width={m.attainment} tone="mint" />
          </>
        ) : (
          <>
            <Bar label="Em aberto" value={brl(m.openAmount)} width={1} tone="dim" />
            <Bar label="Ganho" value={brl(m.wonAmount)} width={m.wonAmount + m.openAmount ? m.wonAmount / (m.wonAmount + m.openAmount) : 0} tone="mint" />
          </>
        )}
        <div className="figs">
          <Fig value={pct(m.winRate)} label="win rate" />
          {m.hasQuota && <Fig value={pct(m.attainment)} label="atingimento" />}
          {m.hasQuota && <Fig value={brl(m.gap)} label="gap" />}
          {m.hasQuota && <Fig value={`${m.coverage.toFixed(1).replace(".", ",")}x`} label={`cobertura (nec. ${m.requiredCoverage.toFixed(1).replace(".", ",")}x)`} />}
          <Fig value={m.hasTiming ? pad2(m.stalled) : "n/d"} label={m.hasTiming ? "parados" : "parados (sem datas)"} />
          <Fig value={pad2(m.lostNoReason.length)} label="perdas sem motivo" />
        </div>
        <Measured>
          {upload
            ? <>Calculado no seu navegador a partir de “{stored?.filename}” ({(m.open.length + m.closed).toLocaleString("pt-BR")} negócios). Nenhum dado saiu deste computador.</>
            : <>Cada número é calculado dos {m.closed + m.open.length} negócios de <code>src/lib/seed.ts</code>. Em produção: <code>serving.v_rep_kpis</code>.</>}
        </Measured>
      </div>

      {!m.hasQuota && upload && <div className="rule-note"><span className="rule-k">Sem meta</span><p>O arquivo de negócios não traz metas, então atingimento, gap e cobertura não são calculados. Metas entram como dataset “Metas” no servidor.</p></div>}
      {m.lowN && (
        <Flag k="Baixa amostra">
          Win rate de {pct(m.winRate)} (IC 95%: {pct(m.ciLow, 0)}–{pct(m.ciHigh, 0)}) com apenas {m.closed} negócios fechados. Abaixo de {MIN_N_RANKING}, o OmniData não compara vendedores. Trate o valor como indicativo.
        </Flag>
      )}
      {m.lostNoReason.length > 0 && (
        <Flag k="Perdas sem motivo estruturado">
          {m.lostNoReason.slice(0, 8).map((d) => d.id).join(", ")}{m.lostNoReason.length > 8 ? ` e mais ${m.lostNoReason.length - 8}` : ""} foram perdidos sem motivo. Análises de win/loss por motivo excluem esses negócios até a resposta do vendedor (48h).
        </Flag>
      )}

      <section>
        <div className="panel-t"><h2 className="h3">Atenção hoje</h2><span className="tag">attention_score</span></div>
        <div className="tbl-wrap">
          <table>
            <thead><tr><th>Negócio</th><th>Dono</th><th>Etapa</th><th className="num">Valor</th><th>Sinais</th></tr></thead>
            <tbody>
              {m.healthRows.slice(0, 5).map((h) => (
                <tr key={h.deal.id}>
                  <td><b>{h.deal.name}</b><span className="sub mono">{h.deal.id}</span></td>
                  <td>{h.deal.owner}</td><td>{h.deal.stage}</td>
                  <td className="num">{brl(h.deal.amount)}</td>
                  <td>{h.flags.join(" · ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export function NegociosView() {
  const { m } = useDashboardData();
  const rows = m.healthRows.slice(0, 200);
  return (
    <>
      <div className="main-head"><div><Eyebrow>Pipeline aberto</Eyebrow><h1 className="h2">Negócios</h1></div>
        <span className="tag">{m.open.length.toLocaleString("pt-BR")} abertos · {brl(m.openAmount)}</span></div>
      <SourceBanner />
      <div className="tbl-wrap">
        <table>
          <thead><tr><th>Negócio</th><th>Dono</th><th>Etapa</th>{m.hasTiming && <th className="num">Dias na etapa</th>}<th className="num">Valor</th><th className="num">Score</th><th>Saúde</th></tr></thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.deal.id}>
                <td><b>{h.deal.name}</b><span className="sub mono">{h.deal.id}</span></td>
                <td>{h.deal.owner}</td><td>{h.deal.stage}</td>
                {m.hasTiming && <td className="num">{h.deal.daysInStage}</td>}
                <td className="num">{brl(h.deal.amount)}</td>
                <td className="num">{Math.round(h.attention).toLocaleString("pt-BR")}</td>
                <td>{h.flags.length ? <span className="gap">{h.flags.join(" · ")}</span> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {m.healthRows.length > rows.length && <p className="note">Mostrando os {rows.length} de maior score, de {m.healthRows.length.toLocaleString("pt-BR")} abertos.</p>}
    </>
  );
}

export function QualidadeView() {
  const { m, source } = useDashboardData();
  const rows: [string, string, string, boolean][] = [
    ["Pontuação preditiva", `${m.closed} fechados`, "≥ 300 por pipeline", m.closed >= 300],
    ["Análise win/loss por motivo", `${pct(m.lossReasonCoverage, 0)} com motivo`, "≥ 80% (meta G2)", m.lossReasonCoverage >= 0.8],
    ["Comparar vendedores", `${m.closed} fechados`, "≥ 20 fechados", !m.lowN],
    ["Previsão de meta", m.hasQuota ? "metas disponíveis" : "sem metas", "metas por vendedor", m.hasQuota],
  ];
  return (
    <>
      <div className="main-head"><div><Eyebrow>omnidata audit</Eyebrow><h1 className="h2">Qualidade dos dados</h1></div></div>
      <SourceBanner />
      <div className="tbl-wrap"><table>
        <thead><tr><th>Caso de uso</th><th>Medido</th><th>Critério</th><th>Decisão</th></tr></thead>
        <tbody>{rows.map(([u, med, crit, ok]) => (
          <tr key={u}><td><b>{u}</b></td><td className="mono">{med}</td><td>{crit}</td>
            <td>{ok ? <span className="tag">go</span> : <span className="tag gap">no-go</span>}</td></tr>))}</tbody>
      </table></div>
      {m.lostNoReason.length > 0 && (
        <Flag k="Sem cobertura de motivo">
          {m.lostNoReason.slice(0, 8).map((d) => d.id).join(", ")}{m.lostNoReason.length > 8 ? ` e mais ${m.lostNoReason.length - 8}` : ""} não têm motivo de perda. Enquanto isso, análises por motivo são consideradas não verificadas.
        </Flag>
      )}
      <FixQueuePanel />
      <div className="ledger"><Measured k="Como reproduzir">
        {source === "upload" ? <>Calculado no seu navegador a partir do arquivo enviado. No servidor, <code>omnidata audit</code> faz a mesma leitura sobre o banco.</>
                             : <>Rode <code>omnidata audit</code> contra o HubSpot para substituir estes números sintéticos pelos reais (M0). Aqui a decisão é derivada de <code>seed.ts</code>.</>}
      </Measured></div>
    </>
  );
}


/** O que corrigir: fila do Coach (Polaris), calculada no navegador. Quem grava a correção é a Lyra, no WhatsApp. */
function FixQueuePanel() {
  const stored = useStored();
  const deals = stored?.deals ?? SEED_DEALS;
  const q = useMemo(() => fixQueue(deals, stored?.records), [deals, stored]);
  if (!q.openDeals) return null;
  const sysLabels = q.issues.filter((i) => i.systemic).map((i) => i.label.toLowerCase());
  return (
    <section className="panel" style={{ marginTop: 28 }}>
      <div className="panel-t"><h2 className="h3">O que corrigir</h2><AgentTag k="polaris" /></div>
      <p className="note">{q.clean} de {q.openDeals} negócios abertos estão completos. Cada linha é um teste sim/não sobre um campo; nada aqui é estimado.</p>
      <div className="tbl-wrap"><table>
        <thead><tr><th>Lacuna</th><th>Quem corrige</th><th>Negócios</th><th>Parcela</th></tr></thead>
        <tbody>{q.issues.map((i) => (
          <tr key={i.code}><td><b>{i.label}</b>{i.systemic && <> <span className="tag gap">quase todos</span></>}</td><td>{i.who === "manager" ? "gestor" : "vendedor"}</td>
            <td className="mono">{i.deals.toLocaleString("pt-BR")}</td><td className="mono">{pct(i.share, 0)}</td></tr>))}</tbody>
      </table></div>
      {sysLabels.length > 0 && (
        <Flag k="Confira antes de cobrar">
          {sysLabels.join(" e ")} aparece em quase todos os negócios. Pode ser limitação do export ou um padrão do CRM, não hábito de cada vendedor. Por isso a fila abaixo só cobra isso nos negócios com valor.
        </Flag>
      )}
      {!q.notesKnown && <p className="note">“Sem nota” não é avaliado nos dados de exemplo; envie um arquivo com notas em Datasets.</p>}
      {q.queue.length > 0 && (
        <>
          <h3 className="h3" style={{ marginTop: 20 }}>Comece por estes ({q.queue.length} de {q.queueTotal})</h3>
          <div className="tbl-wrap"><table>
            <thead><tr><th>Negócio</th><th>Valor</th><th>Primeiro passo</th></tr></thead>
            <tbody>{q.queue.map((r) => (
              <tr key={r.id}><td>{r.name}<div className="note mono">{r.issues.map((c) => q.issues.find((i) => i.code === c)?.label).join(" · ")}</div></td>
                <td className="mono">{r.amount ? brl(r.amount) : "—"}</td><td>{r.firstFix}</td></tr>))}</tbody>
          </table></div>
          <p className="note">Para registrar: no WhatsApp, “Lyra, nota na Acme: …” (a Lyra grava com recibo e Desfazer). A Polaris só lê.</p>
        </>
      )}
      {(q.managerInactive.length > 0 || q.managerDuplicates.length > 0) && (
        <p className="note">Para o gestor: {q.managerInactive.length} negócio(s) com dono desativado e {q.managerDuplicates.length} nome(s) possivelmente duplicado(s).</p>
      )}
    </section>
  );
}
