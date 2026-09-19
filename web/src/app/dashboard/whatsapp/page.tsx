import type { Metadata } from "next";
import { Eyebrow } from "@/components/Ledger";
import { Chat } from "@/components/Chat";
import { owners } from "@/lib/seed";

export const metadata: Metadata = { title: "WhatsApp" };

const status = ["active", "active", "active", "invited"];

export default function WhatsApp() {
  return (
    <>
      <div className="main-head"><div><Eyebrow>Canal</Eyebrow><h1 className="h2">WhatsApp</h1></div></div>
      <div className="grid2">
        <div>
          <div className="panel-t"><h2 className="h3">Vendedores</h2><span className="tag">omnidata user invite</span></div>
          <div className="tbl-wrap"><table>
            <thead><tr><th>Nome</th><th>Papel</th><th>Status</th></tr></thead>
            <tbody>{owners.map((o, i) => (
              <tr key={o.id}><td>{o.name}</td><td>rep</td><td><span className="tag">{status[i]}</span></td></tr>))}</tbody>
          </table></div>
          <p className="note" style={{ marginTop: 14 }}>Convite por template <code>onboarding_v1</code>; “Aceito” registra consentimento (versão do texto + data).</p>
        </div>
        <Chat title="Diego Rocha" msgs={[
          { me: true, text: "quais negócios precisam de ação?" },
          { text: <>Três precisam de você: <b>Mercato – Novo</b> (sem próximo passo), <b>Beta Educação</b> (19 dias parado), <b>Lume Saúde</b> (fechamento vencido).</> },
        ]} />
      </div>
    </>
  );
}
