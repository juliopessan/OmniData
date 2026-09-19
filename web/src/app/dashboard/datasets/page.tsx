import type { Metadata } from "next";
import { Eyebrow } from "@/components/Ledger";
import { DatasetUploader } from "@/components/DatasetUploader";

export const metadata: Metadata = { title: "Datasets" };

const CONNECTORS = [
  ["HubSpot", "Airbyte source-hubspot 6.9.2", "verificado no código do conector", "ativo por INGEST_MODE=airbyte"],
  ["HubSpot (cliente próprio)", "API direta, 15 min", "só testado com simulação", "padrão; também faz as escritas"],
  ["Salesforce", "Airbyte + mapeamento", "modelo, colunas não verificadas", "desativado"],
  ["Pipedrive", "Airbyte + mapeamento", "modelo, colunas não verificadas", "desativado"],
  ["CSV / XLSX", "upload nesta página", "testado com exportação real do HubSpot", "ativo"],
];

export default function Datasets() {
  return (
    <>
      <div className="main-head"><div><Eyebrow>Dados de entrada</Eyebrow><h1 className="h2">Datasets</h1></div></div>
      <p className="body">Suba uma exportação do CRM ou as metas. O arquivo é lido, validado linha a linha e só então entra no banco, sempre de forma idempotente: enviar o mesmo arquivo duas vezes não duplica nada. O conteúdo do arquivo não é guardado, apenas o hash e as contagens.</p>
      <DatasetUploader />
      <section className="stack" style={{ gap: 12 }}>
        <div className="panel-t"><h2 className="h3">Conectores</h2><span className="tag">Airbyte</span></div>
        <div className="tbl-wrap"><table>
          <thead><tr><th>Fonte</th><th>Como</th><th>Situação</th><th>Estado</th></tr></thead>
          <tbody>{CONNECTORS.map(([a, b, c, d]) => <tr key={a}><td><b>{a}</b></td><td>{b}</td><td>{c}</td><td>{d}</td></tr>)}</tbody>
        </table></div>
        <p className="note">Outras fontes do Airbyte entram por mapeamento de colunas em <code>config/integrations.yaml</code>, passando pela mesma validação do upload. Guia: <code>docs/airbyte.md</code>.</p>
      </section>
    </>
  );
}
