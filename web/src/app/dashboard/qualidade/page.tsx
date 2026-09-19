import type { Metadata } from "next";
import { Eyebrow, Flag, Measured } from "@/components/Ledger";
import { computeMetrics, pct } from "@/lib/metrics";

export const metadata: Metadata = { title: "Qualidade dos dados" };

export default function Qualidade() {
  const m = computeMetrics();
  const rows = [
    ["Pontuação preditiva", `${m.closed} fechados`, "≥ 300 por pipeline", m.closed >= 300],
    ["Análise win/loss por motivo", `${pct(m.lossReasonCoverage, 0)} com motivo`, "≥ 80% (meta G2)", m.lossReasonCoverage >= 0.8],
    ["Comparar vendedores", `${m.closed} fechados`, `≥ 20 fechados`, !m.lowN],
    ["Previsão de meta", "metas importadas", "quotas disponíveis", true],
  ] as const;
  return (
    <>
      <div className="main-head"><div><Eyebrow>omnidata audit</Eyebrow><h1 className="h2">Qualidade dos dados</h1></div></div>
      <div className="tbl-wrap"><table>
        <thead><tr><th>Caso de uso</th><th>Medido</th><th>Critério</th><th>Decisão</th></tr></thead>
        <tbody>{rows.map(([u, med, crit, ok]) => (
          <tr key={u}><td><b>{u}</b></td><td className="mono">{med}</td><td>{crit}</td>
            <td>{ok ? <span className="tag">go</span> : <span className="tag gap">no-go</span>}</td></tr>))}</tbody>
      </table></div>
      <Flag k="Sem cobertura de motivo">
        {m.lostNoReason.map((d) => d.id).join(", ")} não têm motivo de perda. Enquanto isso, análises por motivo são consideradas não verificadas.
      </Flag>
      <div className="ledger"><Measured k="Como reproduzir">Rode <code>omnidata audit</code> contra o HubSpot para substituir estes números sintéticos pelos reais (M0). Aqui a decisão é derivada de <code>seed.ts</code>.</Measured></div>
    </>
  );
}
