import type { Metadata } from "next";
import { Eyebrow } from "@/components/Ledger";

export const metadata: Metadata = { title: "Alertas" };

const rules = [
  ["stalled_stage", "Parado na etapa", "Dias na etapa > p75 da etapa (mín. 30 amostras; senão 14 dias)", "stalled:<deal>:<stage>"],
  ["close_date_overdue", "Fechamento vencido", "Negócio aberto com data de fechamento no passado", "overdue:<deal>"],
  ["no_next_step", "Sem próximo passo", "Sem tarefa em 7 dias nem reunião marcada", "nostep:<deal>:<semana>"],
  ["gone_quiet", "Silêncio", "≥ 10 dias sem atividade", "quiet:<deal>:<semana>"],
  ["amount_swing", "Variação de valor", "Mudança > 20% em 7 dias", "swing:<deal>:<data>"],
];
const budget = [["Limite diário por vendedor", "5"], ["Horário de silêncio", "20:00–07:00"], ["Repetição por negócio/regra", "3 dias"], ["Soneca", "3 dias"]];

export default function Alertas() {
  return (
    <>
      <div className="main-head"><div><Eyebrow>Regras de alerta</Eyebrow><h1 className="h2">Alertas</h1></div></div>
      <div className="grid2">
        <div className="tbl-wrap"><table>
          <thead><tr><th>Regra</th><th>Condição</th><th>dedupe_key</th></tr></thead>
          <tbody>{rules.map(([k, t, c, d]) => (
            <tr key={k}><td><b>{t}</b><span className="sub mono">{k}</span></td><td>{c}</td><td className="mono" style={{ fontSize: 12 }}>{d}</td></tr>))}</tbody>
        </table></div>
        <div>
          <div className="panel-t"><h2 className="h3">Orçamento de alertas</h2></div>
          <table><tbody>{budget.map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>)}</tbody></table>
          <p className="note" style={{ marginTop: 14 }}>Ordenação por attention_score (valor em risco). Métricas de efetividade: viewed_at, acted_at em 48h.</p>
        </div>
      </div>
    </>
  );
}
