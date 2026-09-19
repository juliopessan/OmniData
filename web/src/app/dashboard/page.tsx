import { Eyebrow, Bar, Fig, Measured, Flag } from "@/components/Ledger";
import { SpinVerb } from "@/components/SpinVerb";
import { computeMetrics, brl, pct, pad2 } from "@/lib/metrics";
import { PERIOD, MIN_N_RANKING } from "@/lib/seed";

export default function Overview() {
  const m = computeMetrics();
  return (
    <>
      <div className="main-head">
        <div><Eyebrow>Visão geral · {PERIOD}</Eyebrow><h1 className="h2">Livro-razão do time</h1></div>
        <SpinVerb verbs={["Sincronizando HubSpot", "Reconciliando", "Auditando"]} />
      </div>

      <div className="ledger">
        <div className="ledger-head"><span className="live">Livro-razão</span><span className="meta">4 vendedores · dados sintéticos</span></div>
        <Bar label="Meta do time" value={brl(m.quota)} width={1} tone="dim" />
        <Bar label="Ganho no período" value={brl(m.wonAmount)} width={m.attainment} tone="mint" />
        <div className="figs">
          <Fig value={pct(m.attainment)} label="atingimento" />
          <Fig value={brl(m.gap)} label="gap" />
          <Fig value={`${m.coverage.toFixed(1).replace(".", ",")}x`} label={`cobertura (nec. ${m.requiredCoverage.toFixed(1).replace(".", ",")}x)`} />
          <Fig value={pad2(m.stalled)} label="parados" />
        </div>
        <Measured>Cada número acima é calculado a partir dos {m.closed + m.open.length} negócios de <code>src/lib/seed.ts</code> por <code>src/lib/metrics.ts</code>. Em produção: <code>serving.v_rep_kpis</code>, com paridade de 0,5% contra o HubSpot.</Measured>
      </div>

      {m.lowN && (
        <Flag k="Baixa amostra">
          Win rate de {pct(m.winRate)} (IC 95%: {pct(m.ciLow, 0)}–{pct(m.ciHigh, 0)}) com apenas {m.closed} negócios fechados. Abaixo de {MIN_N_RANKING}, o OmniData não compara vendedores. Trate o valor como indicativo.
        </Flag>
      )}
      {m.lostNoReason.length > 0 && (
        <Flag k="Perdas sem motivo estruturado">
          {m.lostNoReason.map((d) => d.id).join(", ")} foram perdidos sem motivo. Análises de win/loss por motivo excluem esses negócios até a resposta do vendedor (48h).
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
