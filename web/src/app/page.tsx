import Link from "next/link";
import { SiteHeader, SiteFooter } from "@/components/SiteChrome";
import { Eyebrow, Bar, Fig, Measured, Flag } from "@/components/Ledger";
import { Chat } from "@/components/Chat";
import { TeamGrid } from "@/components/TeamGrid";
import { SpinVerb } from "@/components/SpinVerb";
import { computeMetrics, brl, pct, pad2 } from "@/lib/metrics";

export default function Home() {
  const m = computeMetrics();
  return (
    <>
      <SiteHeader />
      <main>
        <div className="wrap hero">
          <div className="stack" style={{ gap: 26 }}>
            <Eyebrow>Inteligência de vendas · HubSpot + WhatsApp</Eyebrow>
            <h1 className="display">Seu CRM atualizado por quem <span className="voice">vende.</span></h1>
            <p className="lede">
              O vendedor não abre dashboards. O OmniData leva a análise e as ações do HubSpot para o WhatsApp dele — e captura
              o dado que falta (motivo de perda, próximo passo) na origem, por áudio ou um toque.
            </p>
            <div className="actions">
              <Link href="/cadastro" className="btn">Começar agora →</Link>
              <Link href="/dashboard" className="btn ghost">Ver demonstração</Link>
            </div>
            <SpinVerb verbs={["Sincronizando HubSpot", "Reconciliando negócios", "Calibrando alertas", "Pontuando pipeline", "Auditando motivos de perda"]} />
          </div>

          <div className="ledger" aria-label="Livro-razão de exemplo, calculado a partir de dados sintéticos">
            <div className="ledger-head"><span className="live">Livro-razão · {`set/2026`}</span><span className="meta">dados sintéticos</span></div>
            <Bar label="Meta do time" value={brl(m.quota)} width={1} tone="dim" />
            <Bar label="Ganho no período" value={brl(m.wonAmount)} width={m.attainment} tone="mint" />
            <div className="figs">
              <Fig value={pct(m.winRate)} label="win rate" />
              <Fig value={pad2(m.stalled)} label="negócios parados" />
              <Fig value={pad2(m.lostNoReason.length)} label="perdas sem motivo" />
              <Fig value={`${pct(m.ciLow, 0)}–${pct(m.ciHigh, 0)}`} label="IC 95%" />
            </div>
            <Measured>Calculado a partir de {deals(m.closed)} sintéticos em <code>src/lib/seed.ts</code>. Recarregue e confira: os números vêm do código, não de texto.</Measured>
          </div>
        </div>

        <section className="section">
          <div className="wrap stack" style={{ gap: 40 }}>
            <div className="stack"><Eyebrow>Como funciona</Eyebrow>
              <h2 className="h2">Do CRM ao WhatsApp em quatro passos.</h2></div>
            <div className="seq">
              {[
                ["01", "Ingestão", "Sincroniza HubSpot a cada 15 minutos: negócios, contatos, atividades e histórico de etapas."],
                ["02", "Métricas em SQL", "Win rate com intervalo de confiança, cobertura de meta e saúde do negócio — calculados, nunca “estimados” pelo modelo."],
                ["03", "Regras e alertas", "Cinco regras, orçamento diário, horário de silêncio e soneca. Só chega o que importa."],
                ["04", "WhatsApp", "Perguntas, notas, tarefas e mudanças de etapa por chat. Toda escrita tem recibo e Desfazer por 24h."],
              ].map(([n, t, b]) => (
                <div key={n}><span className="n">{n}</span><h3 className="h3">{t}</h3><p className="body">{b}</p></div>
              ))}
            </div>
          </div>
        </section>

        <section className="section" id="equipe">
          <div className="wrap stack" style={{ gap: 32 }}>
            <div className="stack"><Eyebrow>O Observatório</Eyebrow>
              <h2 className="h2">Uma equipe de assessores, uma conversa só.</h2>
              <p className="lede">Orion lê o pedido e divide o trabalho. Cada especialista responde assinando o próprio nome, e você recebe tudo numa mensagem.</p></div>
            <TeamGrid />
          </div>
        </section>

        <section className="section">
          <div className="wrap grid2" style={{ alignItems: "center" }}>
            <div className="stack">
              <Eyebrow>Na prática</Eyebrow>
              <h2 className="h2">Registrar a reunião leva segundos.</h2>
              <p className="body">Áudio vira nota, próximo passo e proposta de nova data de fechamento. Ações de baixo risco executam na hora; as de alto risco pedem confirmação.</p>
              <Link href="/funcionalidades" className="btn ghost" style={{ alignSelf: "flex-start" }}>Ver todas as funcionalidades</Link>
            </div>
            <Chat title="Ana Souza" msgs={[
              { me: true, text: "🎤 áudio 0:22 — “reunião com o CFO da Acme, proposta na sexta”" },
              { text: <>Registrei ✅ <b>Nota</b> em <b>Acme – Renovação</b>. Criei a tarefa “Enviar proposta” para sexta.</>, buttons: ["Editar", "Desfazer"] },
              { text: <>Mover <b>Acme – Renovação</b> de <b>Proposta</b> para <b>Negociação</b>?</>, buttons: ["Confirmar", "Ajustar", "Cancelar"] },
            ]} />
          </div>
        </section>

        <section className="section" id="seguranca">
          <div className="wrap stack" style={{ gap: 28 }}>
            <div className="stack"><Eyebrow>Confiança</Eyebrow>
              <h2 className="h2">Número na tela vem do SQL, nunca do modelo.</h2>
              <p className="lede">O LLM escolhe a ferramenta e redige a resposta. Um guarda de números descarta qualquer texto cujo valor não esteja no JSON da ferramenta.</p></div>
            <div className="grid2" style={{ alignItems: "stretch" }}>
              <div className="stack">
                <h3 className="h3">Permissões no código, não no prompt</h3>
                <p className="body">Vendedor vê os próprios negócios; gestor, o time; admin, tudo. Nenhuma ferramenta aceita um owner vindo do modelo. Consentimento LGPD registrado e dados apagáveis sob demanda.</p>
              </div>
              <Flag k="Baixa amostra">Só {m.closed} negócios fechados no período — pouco para comparar vendedores com segurança. O OmniData suprime rankings abaixo de 20 fechados e diz isso na resposta.</Flag>
            </div>
          </div>
        </section>

        <section className="section">
          <div className="wrap stack" style={{ alignItems: "flex-start" }}>
            <h2 className="h2" style={{ maxWidth: "18ch" }}>Comece com dados sintéticos. Conecte o HubSpot quando estiver pronto.</h2>
            <Link href="/cadastro" className="btn">Começar agora →</Link>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}

function deals(n: number) { return `${n} negócios fechados`; }
