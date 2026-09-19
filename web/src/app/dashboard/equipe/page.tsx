import type { Metadata } from "next";
import { Eyebrow } from "@/components/Ledger";
import { TeamGrid } from "@/components/TeamGrid";
import { TEAM } from "@/lib/team";

export const metadata: Metadata = { title: "Equipe" };

export default function Equipe() {
  return (
    <>
      <div className="main-head"><div><Eyebrow>{TEAM.name}</Eyebrow><h1 className="h2">Equipe de assessores</h1></div></div>
      <p className="body">{TEAM.tagline} Cada membro só pode chamar as ferramentas listadas abaixo: quem decide isso é o código, não o modelo.</p>
      <TeamGrid withTools />
      <div className="rule-note">
        <span className="rule-k">Regras do plano</span>
        <p>Orion monta planos de até 3 passos. Um plano tem no máximo uma escrita no CRM, e ela vem por último. Escritas de alto risco sempre pedem confirmação; planos inválidos são descartados.</p>
      </div>
    </>
  );
}
