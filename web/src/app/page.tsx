import Link from "next/link";
import { SiteHeader, SiteFooter } from "@/components/SiteChrome";
import { Eyebrow, Bar, Fig, Measured, Flag } from "@/components/Ledger";
import { Chat } from "@/components/Chat";
import { TeamGrid } from "@/components/TeamGrid";
import { SpinVerb } from "@/components/SpinVerb";
import { computeMetrics, brl, pct, pad2 } from "@/lib/metrics";

/**
 * Estrutura da landing: HOOK → RE-HOOK → MEAT → CTA.
 *  HOOK     prende com uma verdade que o gestor reconhece (o time não abre o CRM) e já apresenta a equipe.
 *  RE-HOOK  reengaja com o problema real, mostrado em dado calculado (a flag), e vira a pergunta que abre o miolo.
 *  MEAT     o Observatório: quem é quem, um dia de trabalho, como funciona por baixo, por que dá para confiar.
 *  CTA      um único convite, sem promessa que o produto não cumpre.
 * Todo número vem de web/src/lib/metrics.ts (dados sintéticos); nada é digitado no JSX.
 */
export default function Home() {
  const m = computeMetrics();
  const top = m.healthRows[0].deal;
  const quiet = m.open.find((d) => d.id === "D-1002")!;
  return (
    <>
      <SiteHeader />
      <main>
        {/* ───────────── HOOK ───────────── */}
        <div className="wrap hero" id="hook">
          <div className="stack" style={{ gap: 26 }}>
            <Eyebrow>Observatório · inteligência de vendas no WhatsApp</Eyebrow>
            <h1 className="display">Seu time não abre o CRM. Mas <span className="voice">responde</span> o WhatsApp.</h1>
            <p className="lede">
              Conheça o Observatório: seis assessores de IA que vivem na conversa do seu vendedor, atualizam o HubSpot por ele
              e avisam o que precisa de ação antes que o negócio esfrie.
            </p>
            <div className="actions">
              <Link href="/cadastro" className="btn">Começar agora →</Link>
              <Link href="#equipe" className="btn ghost">Conhecer a equipe</Link>
            </div>
            <SpinVerb verbs={["Orion coordenando", "Vega calculando a meta", "Altair varrendo o funil", "Lyra registrando no HubSpot", "Argus auditando os dados"]} />
          </div>

          <div className="ledger" aria-label="Livro-razão de exemplo, calculado a partir de dados sintéticos">
            <div className="ledger-head"><span className="live">Livro-razão · set/2026</span><span className="meta">dados sintéticos</span></div>
            <Bar label="Meta do time" value={brl(m.quota)} width={1} tone="dim" />
            <Bar label="Ganho no período" value={brl(m.wonAmount)} width={m.attainment} tone="mint" />
            <div className="figs">
              <Fig value={pct(m.winRate)} label="win rate" />
              <Fig value={pad2(m.stalled)} label="negócios parados" />
              <Fig value={pad2(m.lostNoReason.length)} label="perdas sem motivo" />
              <Fig value={`${pct(m.ciLow, 0)}–${pct(m.ciHigh, 0)}`} label="IC 95%" />
            </div>
            <Measured>Calculado a partir de {m.closed + m.open.length} negócios sintéticos em <code>src/lib/seed.ts</code>. Recarregue e confira: os números vêm do código, não de texto.</Measured>
          </div>
        </div>

        {/* ───────────── RE-HOOK ───────────── */}
        <section className="section" id="rehook">
          <div className="wrap stack" style={{ gap: 40 }}>
            <div className="stack">
              <Eyebrow>O problema real</Eyebrow>
              <h2 className="h2" style={{ maxWidth: "22ch" }}>O dado não falta por preguiça. Falta porque o caminho até ele é longo.</h2>
              <p className="lede">Dashboard ninguém abre, CRM ninguém atualiza. Sobra um forecast em cima de números que ninguém consegue defender.</p>
            </div>

            <div className="symptoms">
              {[
                ["Lyra", "O vendedor atualiza o CRM na sexta à noite, se lembrar.", "Lyra registra a nota ou a tarefa na hora, por texto ou áudio, com recibo e Desfazer por 24h."],
                ["Altair", "O negócio esfria e ninguém vê até o fim do trimestre.", "Altair aponta o que está parado, sem próximo passo ou com a data vencida, do mais valioso ao menos."],
                ["Vega", "O forecast é discutido com números que ninguém consegue defender.", "Vega só usa número calculado em SQL. Nada de conta feita pelo modelo."],
                ["Argus", "A amostra é pequena e todo mundo compara vendedores mesmo assim.", "Argus avisa quando não dá para confiar, e o OmniData suprime o ranking abaixo de 20 fechados."],
              ].map(([who, before, after]) => (
                <div key={who} className="symptom">
                  <p className="before">{before}</p>
                  <span className="arrow" aria-hidden="true">→</span>
                  <p className="after"><b>{who}:</b> {after}</p>
                </div>
              ))}
            </div>

            <Flag k="Perdas sem motivo estruturado">
              {m.lostNoReason.map((d) => d.id).join(", ")} foram perdidos sem motivo registrado. Análises de win/loss por motivo excluem esses negócios até o vendedor responder. Este é o buraco que o Observatório existe para fechar.
            </Flag>

            <h3 className="h2" style={{ maxWidth: "20ch" }}>E se o CRM se atualizasse na própria conversa?</h3>
          </div>
        </section>

        {/* ───────────── MEAT ───────────── */}
        <section className="section" id="equipe">
          <div className="wrap stack" style={{ gap: 32 }}>
            <div className="stack">
              <Eyebrow>Conheça o Observatório</Eyebrow>
              <h2 className="h2">Seis assessores. Uma conversa. Cada um assina o que fez.</h2>
              <p className="lede">Orion lê o pedido e divide o trabalho. Cada especialista só usa as ferramentas que são dele, e você recebe tudo numa mensagem, com o nome de quem cuidou de cada parte.</p>
            </div>
            <TeamGrid />
          </div>
        </section>

        <section className="section" id="dia">
          <div className="wrap grid2" style={{ alignItems: "start" }}>
            <div className="stack" style={{ gap: 28 }}>
              <div className="stack">
                <Eyebrow>Um dia com o Observatório</Eyebrow>
                <h2 className="h2">Da primeira mensagem da manhã ao último aviso da tarde.</h2>
              </div>
              <ol className="day">
                <li><time>07:30</time><div><b>Aurora</b><p>Abre o dia: os {Math.min(5, m.healthRows.length)} negócios que mais pedem a Ana, começando por <em>{top.name}</em>, parado há {top.daysInStage} dias.</p></div></li>
                <li><time>10:12</time><div><b>Orion → Vega e Lyra</b><p>Ana pede duas coisas numa frase. Orion divide: Vega responde a meta, Lyra registra a nota. Uma resposta só.</p></div></li>
                <li><time>14:05</time><div><b>Altair</b><p><em>{quiet.name}</em> está há {quiet.quietDays} dias sem atividade e com a data de fechamento vencida. Um toque para ver, outro para adiar.</p></div></li>
                <li><time>17:40</time><div><b>Argus</b><p>Só {m.closed} negócios fechados no período. Ele avisa para não comparar vendedores ainda.</p></div></li>
              </ol>
            </div>
            <Chat title="Ana Souza" msgs={[
              { me: true, text: "como estou na meta e anota na Acme que o CFO aprovou" },
              { text: <><b>Vega</b>: Você está em <b>{pct(m.attainment)}</b> da meta. Falta <b>{brl(m.gap)}</b>.<br /><br /><b>Lyra</b>: Registrei ✅ <b>Nota</b> em <b>Acme – Renovação</b>.</>, buttons: ["Editar", "Desfazer"] },
              { text: <><b>Lyra</b>: Mover <b>Acme – Renovação</b> de <b>Proposta</b> para <b>Negociação</b>?</>, buttons: ["Confirmar", "Ajustar", "Cancelar"] },
            ]} />
          </div>
        </section>

        <section className="section">
          <div className="wrap stack" style={{ gap: 40 }}>
            <div className="stack"><Eyebrow>Por baixo do capô</Eyebrow>
              <h2 className="h2">Do CRM ao WhatsApp em quatro passos.</h2></div>
            <div className="seq">
              {[
                ["01", "Ingestão", "Sincroniza o HubSpot a cada 15 minutos: negócios, contatos, atividades e histórico de etapas."],
                ["02", "Métricas em SQL", "Win rate com intervalo de confiança, cobertura de meta e saúde do negócio, calculados e nunca “estimados” pelo modelo."],
                ["03", "Plano do Orion", "O modelo propõe até 3 passos; o código valida quem pode chamar o quê. No máximo uma escrita, e por último."],
                ["04", "Resposta assinada", "Cada especialista escreve a sua parte. Toda escrita tem recibo e Desfazer por 24h; as sensíveis pedem confirmação."],
              ].map(([n, t, b]) => (
                <div key={n}><span className="n">{n}</span><h3 className="h3">{t}</h3><p className="body">{b}</p></div>
              ))}
            </div>
          </div>
        </section>

        <section className="section" id="seguranca">
          <div className="wrap stack" style={{ gap: 28 }}>
            <div className="stack"><Eyebrow>Confiança</Eyebrow>
              <h2 className="h2">Número na tela vem do SQL, nunca do modelo.</h2>
              <p className="lede">Um guarda de números descarta qualquer texto cujo valor não esteja no resultado da ferramenta. Argus faz o resto: diz onde os dados não sustentam a conclusão.</p></div>
            <div className="grid2" style={{ alignItems: "stretch" }}>
              <div className="stack">
                <h3 className="h3">Permissões no código, não no prompt</h3>
                <p className="body">Vendedor vê os próprios negócios; gestor, o time; admin, tudo. Nenhuma ferramenta aceita um dono vindo do modelo, e nenhum assessor chama uma ferramenta fora da própria lista. Consentimento LGPD registrado e dados apagáveis sob demanda.</p>
              </div>
              <Flag k="Baixa amostra">Só {m.closed} negócios fechados no período, pouco para comparar vendedores com segurança. O OmniData suprime rankings abaixo de 20 fechados e diz isso na resposta.</Flag>
            </div>
          </div>
        </section>

        {/* ───────────── CTA ───────────── */}
        <section className="section cta" id="cta">
          <div className="wrap stack" style={{ alignItems: "flex-start", gap: 24 }}>
            <Eyebrow>Comece pelo pipeline</Eyebrow>
            <h2 className="display" style={{ fontSize: "clamp(36px, 5.5vw, 68px)", maxWidth: "16ch" }}>Coloque o Observatório para trabalhar.</h2>
            <p className="lede">Comece com dados sintéticos e conecte o HubSpot quando estiver pronto. Preços sob consulta, dimensionados ao tamanho do time.</p>
            <div className="actions">
              <Link href="/cadastro" className="btn">Começar agora →</Link>
              <Link href="/precos" className="btn ghost">Falar com vendas</Link>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
