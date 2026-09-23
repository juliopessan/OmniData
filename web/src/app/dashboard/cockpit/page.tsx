import type { Metadata } from "next";
import { Cockpit } from "@/components/Cockpit";
import { Eyebrow } from "@/components/Ledger";

export const metadata: Metadata = { title: "Cockpit de Vendas" };

export default function CockpitPage() {
  return (
    <>
      <div className="main-head"><div><Eyebrow>Acompanhamento</Eyebrow><h1 className="h2">Cockpit de Vendas</h1></div></div>
      <p className="body">Conversas reais dos vendedores com a equipe no WhatsApp, para a gestão acompanhar sem precisar abrir o telefone de ninguém.</p>
      <Cockpit />
    </>
  );
}
