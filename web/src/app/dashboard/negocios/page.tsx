import type { Metadata } from "next";
import { Eyebrow } from "@/components/Ledger";
import { computeMetrics, brl } from "@/lib/metrics";

export const metadata: Metadata = { title: "Negócios" };

export default function Negocios() {
  const m = computeMetrics();
  return (
    <>
      <div className="main-head"><div><Eyebrow>Pipeline aberto</Eyebrow><h1 className="h2">Negócios</h1></div>
        <span className="tag">{m.open.length} abertos · {brl(m.openAmount)}</span></div>
      <div className="tbl-wrap">
        <table>
          <thead><tr><th>Negócio</th><th>Dono</th><th>Etapa</th><th className="num">Dias na etapa</th><th className="num">Valor</th><th className="num">Score</th><th>Saúde</th></tr></thead>
          <tbody>
            {m.healthRows.map((h) => (
              <tr key={h.deal.id}>
                <td><b>{h.deal.name}</b><span className="sub mono">{h.deal.id}</span></td>
                <td>{h.deal.owner}</td><td>{h.deal.stage}</td>
                <td className="num">{h.deal.daysInStage}</td>
                <td className="num">{brl(h.deal.amount)}</td>
                <td className="num">{Math.round(h.attention).toLocaleString("pt-BR")}</td>
                <td>{h.flags.length ? <span className="gap">{h.flags.join(" · ")}</span> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
