# OmniData

**Seu time não abre o CRM. Mas responde o WhatsApp.**

<p align="center"><img src="docs/assets/hero.png" alt="Landing do OmniData: o hero com os números do time calculados a partir de dados sintéticos" width="900"></p>

**Demo do site:** https://omnidata-web-eta.vercel.app (dados sintéticos; login e cadastro são só demonstração).

<sub>Screenshot gerado por `scripts/screenshot-hero.sh` (Chrome headless sobre o build de produção). Os números do hero são calculados de dados sintéticos.</sub>

## O problema

O vendedor não esquece de atualizar o CRM por preguiça. Ele esquece porque o caminho até lá é longo: abrir o HubSpot, achar o negócio certo, lembrar o que foi dito na ligação de duas horas atrás. Então ele atualiza na sexta à noite, se lembrar — e o negócio que esfriou na terça só aparece pro gestor no fim do trimestre, quando já não dá mais pra fazer nada.

O forecast vira uma discussão de números que ninguém consegue defender, porque ninguém sabe se vieram de um SQL ou de um chute do modelo. A amostra às vezes é pequena demais pra comparar vendedor com vendedor, e mesmo assim vira ranking. E o gestor, que devia acompanhar como o time está conduzindo as conversas de venda, não tem outro jeito de ver isso a não ser pedindo pra alguém abrir o celular.

O único lugar onde o vendedor já está, todo dia, sem precisar de treinamento nem lembrete, é o WhatsApp.

## O que o OmniData faz

O OmniData leva a inteligência do HubSpot para dentro dessa conversa. Quem cuida dela é o **Observatório**, uma equipe de dez assessores de IA — Orion coordena, e cada especialista (Vega, Altair, Lyra, Aurora, Argus, Polaris, Nova, Atlas, Vela) responde só o que é da própria área, assinando a própria parte.

1. O vendedor manda uma mensagem no WhatsApp — texto ou áudio, pergunta ou "nota na Acme: CFO aprovou o escopo".
2. Orion lê o pedido, decide quem da equipe resolve (às vezes mais de um especialista, num plano curto) e devolve **uma resposta só**, assinada por quem cuidou de cada parte.
3. Todo número que aparece vem do SQL, calculado contra o HubSpot real — nunca de uma conta feita pelo modelo. Se o dado não sustenta a pergunta (amostra pequena, cobertura baixa), o Argus avisa em vez de inventar confiança.
4. Uma escrita no CRM (nota, tarefa, mudança de etapa) sempre pede confirmação antes de gravar, e pode ser desfeita em até 24h.
5. De manhã, um resumo proativo do que precisa de atenção; às 18h, um recap do que foi feito no dia e sugestão pra manhã seguinte — sem virar spam.
6. O vendedor define a própria meta ("quero fechar 3 negócios até sexta") e acompanha o progresso dentro da mesma conversa.
7. Antes de uma reunião difícil, a Nova prepara um script com base no que já foi registrado (motivos de perda, dores reais); a Atlas lembra, com a citação exata, o que já foi dito numa reunião passada — nunca um resumo inventado.
8. O gestor abre o **Cockpit de Vendas** no navegador e acompanha as conversas de todo o time em tempo real, sem precisar abrir o telefone de ninguém.

## Como funciona por baixo

O ponto que sustenta tudo isso: **o LLM só propõe, o código decide**. Cada especialista tem uma lista fechada de ferramentas que pode chamar (`agents/team.py`), e o plano do Orion passa por validação antes de rodar — no máximo 3 passos, no máximo 1 escrita, sempre por último. Um modelo nunca recebe a permissão de outro usuário nem decide sozinho o que grava no CRM; quem decide quem pode ver o quê é sempre o Postgres, via `Principal.owner_clause()`.

A maior parte da inteligência do produto não usa LLM nenhum: previsão de forecast (Vega), coach de qualidade de dados (Polaris) e insights de empresas (dores, termos, ERPs) são cálculo determinístico — SQL e estatística puros, testados bit a bit contra a mesma implementação em TypeScript que roda no navegador. O modelo de linguagem entra só nas duas pontas que exigem entender linguagem natural: decidir qual especialista responde, e narrar o resultado em português — nunca fazer conta, nunca escrever SQL, nunca ver dado pessoal bruto.

O canal é a [Evolution API](https://docs.evolutionfoundation.com.br), auto-hospedada sobre o protocolo do WhatsApp Web (Baileys) — não a API oficial da Meta, então sem verificação de negócio nem aprovação de template, mas também sem ser um canal sancionado pelo WhatsApp. Quando o [Langfuse](https://langfuse.com) está configurado (`telemetry.py`, opcional e auto-hospedado), cada mensagem processada vira um trace: dá pra ver, por conversa, qual especialista respondeu, quanto custou em tokens e onde a resposta saiu do previsto — sem ele, o bot funciona exatamente igual, só sem essa visibilidade.

O painel web (`web/`) por padrão mostra dados sintéticos calculados no navegador — dá pra ver o produto inteiro sem conta em HubSpot, Meta, OpenAI ou Anthropic. Uma conta real entra por trás, sem o usuário perceber a troca.

## Estado atual

| Peça | Estado |
|---|---|
| Front-end (landing, funcionalidades, preços, login, cadastro, dashboard) | Pronto, no ar na Vercel |
| Banco, migrations, views `gold`/`serving`, backup | Pronto e testado contra Postgres real |
| Ingestão do HubSpot (backfill retomável, incremental, histórico, snapshots, `audit`) | Pronto; **testado só com fixtures e HubSpot simulado** |
| Bot no WhatsApp (webhook, fila, orquestrador, alertas, resumo matinal e recap noturno), via Evolution API (ADR 0008) | **Em produção**, num VPS real, com `api` + `worker` + Postgres, HTTPS via Traefik ([docs/deploy-vps.md](docs/deploy-vps.md)). Verificado com conversas reais: ativação, escritas com confirmação, áudio, meta pessoal e os dez especialistas respondendo com LLM real, 0 erro — contra a base seedada (`dev seed`), ainda não HubSpot real |
| Observatório (Orion planeja, especialistas executam; resolutivo — resolve referências à troca anterior, ex. "essas causas") | Pronto. Avaliação do planejador: conjunto de 68 frases + 17 inéditas (`omnidata eval planner`) |
| Cockpit de Vendas (`/dashboard/cockpit`): conversas reais do WhatsApp, para o gestor acompanhar sem abrir o telefone de ninguém | Pronto e em produção |
| Observabilidade (Langfuse, `telemetry.py`, opcional): um trace por mensagem, com custo, latência e o plano que o Orion decidiu | Pronto e em produção, verificado contra uma instância real |
| Áudios do WhatsApp (transcrição) | Pronto e em produção (OpenAI) |
| Upload de datasets (CSV/XLSX de negócios e metas): página, API e CLI | Pronto; testado com uma exportação real do HubSpot (1000 negócios) e no navegador |
| Airbyte como camada de conectores (HubSpot + outras fontes por mapeamento) | Pronto no código; **nunca rodou contra um Airbyte real** ([docs/airbyte.md](docs/airbyte.md)) |
| Insights de empresas (dores, termos, ERPs, tipo de demanda), com os agentes; painel `/dashboard/insights` | Pronto; testado com dataset sintético e com um export real do HubSpot |
| Propostas em PDF por e-mail e WhatsApp (Vela) | **Em produção**; verificado de ponta a ponta em 25/09/2026 (e-mail real via Gmail API + OAuth2, documento real via Evolution), além de unitários + e2e contra Postgres real |
| dbt | Não implementado (ADR 0002) |

Veja **[docs/go-live.md](docs/go-live.md)** para o que ainda depende das suas próprias contas (HubSpot, Meta/número de WhatsApp).

## O Observatório (harness agêntico, ADR 0003)

| Membro | Função | Ferramentas |
|---|---|---|
| **Orion** | Coordenador: analisa o pedido, monta o plano (≤ 3 passos) e devolve uma resposta só | — |
| **Vega** | Analista de Metas, segmentos, previsão e — pra gestores — status do time inteiro | `get_kpis`, `get_quota_status`, `get_segment_insights`, `get_forecast`, `get_team_status` |
| **Altair** | Gerente de Pipeline, demanda e ERPs | `get_pipeline_summary`, `get_deal`, `list_deals_needing_action`, `get_demand_types`, `get_systems_landscape` |
| **Lyra** | Escriba do CRM e leitora de notas (dores, termos) | `add_note`, `create_task`, `propose_deal_update`, `undo_last`, `get_pains`, `get_recurring_terms` |
| **Aurora** | Rotina, alertas, insight do dia e meta pessoal do vendedor | `get_morning_brief`, `get_insight_digest`, `set_goal`, `get_goal_status` |
| **Argus** | Auditor de Confiança | `get_data_quality`, `get_insight_coverage` |
| **Polaris** | Coach de Qualidade: transforma a auditoria em fila de correção por vendedor (só lê; a Lyra grava) | `get_fix_queue` |
| **Nova** | Coach de Vendas: script e quebra de objeção a partir do que já foi registrado | `get_playbook`, `search_meeting_notes` |
| **Atlas** | Memória de Reuniões: busca por assunto no que já foi dito, sempre citação real | `search_meeting_notes` |
| **Vela** | Especialista em Propostas: monta um PDF a partir do negócio e manda pro cliente por e-mail e/ou WhatsApp, sempre com confirmação | `send_proposal` |

O LLM só *propõe* o plano; o código valida (allowlist por especialista, no máximo 1 escrita e por último). Endereçamento direto: “Vega, como estou na meta?”. `uv run omnidata team` lista a equipe; `team export` gera `web/src/lib/team.json` (um teste garante a sincronia). `search_meeting_notes` é a única ferramenta com dois donos legítimos (Nova e Atlas) — a resposta é assinada por quem o Orion realmente planejou, não por um dono fixo.

**WhatsApp (Evolution API, ADR 0008):** o gateway é a [Evolution API](https://docs.evolutionfoundation.com.br), auto-hospedada, sobre o protocolo do WhatsApp Web (Baileys). Ligar o número:

```bash
omnidata evolution create-instance --name omnidata --webhook-url https://<sua-api>/webhooks/evolution   # salva um QR code
# abra o arquivo salvo e escaneie com o WhatsApp do número que vai rodar o bot (Config. → Aparelhos conectados)
omnidata evolution status --name omnidata   # repita até aparecer "open"
```

Depois, `EVOLUTION_INSTANCE=omnidata` no `.env`. Sem assinatura nativa de webhook (diferente do Meta): `EVOLUTION_WEBHOOK_SECRET` é um valor que você inventa e a Evolution devolve como cabeçalho a cada chamada, conferido em tempo constante. Botões e listas viram texto numerado (a UI nativa do Baileys não é confiável nos aparelhos reais). Mensagens de grupo nunca chegam a um Principal — só uma conversa 1:1 com o número do bot é processada.

**Áudios do WhatsApp:** transcritos com `gpt-transcribe` (OpenAI, US$ 0,0045/min; fallback `gpt-4o-mini-transcribe`), decodificados para WAV via ffmpeg, com limite de 180 s e orçamento diário por usuário. O bot mostra “Entendi: …” antes de responder, e escritas de risco continuam pedindo confirmação. Sem Azure no projeto (ADR 0004). Para escolher o modelo com seus áudios: `scripts/bench_transcribe.py`.

**Conversa humanizada:** um "digitando..." pulsado (liga, pausa, liga de novo) até a resposta ficar pronta, uma reação de 👍 num "valeu" solto em vez de repetir o menu, e o tom da narração muda com o sentimento detectado no texto (frustração, pressa) — tudo por regra determinística, nunca uma chamada extra ao modelo.

## Cockpit de Vendas

`/dashboard/cockpit`: as conversas reais do WhatsApp, para a gestão acompanhar sem precisar abrir o telefone de ninguém — a mesma dor que motiva o resto do produto, só que do lado do gestor. Lê direto do `app.wa_message` que o bot já grava a cada mensagem enviada e recebida; nenhum dado novo, nenhuma escrita própria.

## Observabilidade (Langfuse)

`telemetry.py`: opcional, liga sozinho quando `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` e `LANGFUSE_BASE_URL` estão no `.env` — sem eles, o bot funciona exatamente igual, só sem os traces. Cada mensagem processada vira um trace (`bot/orchestrator.py::handle`): a decisão do Orion, a ferramenta que cada especialista chamou e a narração final, com modelo, tokens e latência de cada chamada ao LLM. Nenhum texto entra num trace sem antes passar pela mesma máscara de PII usada em toda chamada ao modelo.

## Dados de entrada

- **Upload:** `/dashboard/datasets` (arrastar-e-soltar, prévia, relatório de erros por linha) ou `uv run omnidata dataset import arquivo.csv --kind deals --apply`. Reconhece a exportação do HubSpot em pt-BR, tira ganho/perdido da etapa e o motivo de perda das notas. Detalhes em [docs/datasets.md](docs/datasets.md).
- **Airbyte:** HubSpot e outras fontes aterrissam no Postgres e o OmniData mapeia para o `silver` (`INGEST_MODE=airbyte`). O cliente próprio do HubSpot continua sendo o padrão e o único que escreve no CRM. Guia em [docs/airbyte.md](docs/airbyte.md).

**Reunião de vendas** (`/dashboard/reuniao`): uma página para conduzir a reunião de vendas com o seu arquivo. Traz os KPIs, gráficos (pipeline e concentração, demanda, ERPs, dores e termos, lacunas de qualidade e cobertura) e **decisões sugeridas por regras fixas** (`web/src/lib/decisions.ts`): cada sugestão mostra a regra que a disparou, os números que a sustentam e o agente responsável, e vem rotulada como sugestão para não se confundir com número medido. Imprime em PDF pelo navegador. Tudo é calculado no navegador; não usa plataforma de BI nem modelo de linguagem. Um BI (por exemplo o Metabase, lendo `serving.*`) só faz sentido depois que a API e o Postgres estiverem no ar.

**Previsão (Vega, `get_forecast`; `omnidata forecast analyze <arquivo> --quota N`):** estimativa estatística de quanto o pipeline aberto ainda pode render e da chance de bater a meta. Usa a taxa de ganho dos negócios fechados (com intervalo de confiança de Wilson) em três cenários (baixo, central, alto) simulados com os mesmos números aleatórios, e mostra faixas (10% a 90%), nunca um número só. Recusa prever com menos de 10 fechados e marca como “teto, não previsão” quando os negócios abertos com valor são mais de 3 vezes os fechados, porque a taxa do passado não descreve um acúmulo de negócios parados. Determinística (semente fixa) e igual no bot e no navegador, com teste que executa o TypeScript no Node e compara com o Python. **O modelo de ML (scikit-learn) está desligado de propósito:** o projeto exige 300 fechados por pipeline e os exports não trazem data de criação nem histórico de etapa, então um modelo aprenderia o resultado em vez de prevê-lo (ADR 0007).

**Coach (Polaris):** `/dashboard/qualidade` mostra “O que corrigir” e, no WhatsApp, “o que preciso corrigir?” devolve os negócios com lacunas (sem valor, data vencida, sem próximo passo, sem nota, nome fora do padrão), ordenados por valor. Se uma lacuna aparece em quase todos os negócios (≥ 90%), ele avisa que pode ser do export ou do padrão do CRM, em vez de cobrar cada vendedor. Dono desativado e duplicatas vão só para o gestor. A Polaris não escreve no CRM: a correção passa pela Lyra, com confirmação. `omnidata hygiene analyze <arquivo>` roda sem banco.

**Insights de empresas** (`/dashboard/insights`, `omnidata insights analyze <arquivo>`): dores, termos recorrentes, ERPs/CRMs, tipo de demanda, segmentos e campanhas, extraídos das notas e dos nomes dos negócios por contagem determinística (sem LLM). Lyra cuida de dores e termos, Altair de demanda e ERPs, Vega de segmentos, Argus da cobertura e Aurora do insight do dia; o Orion junta tudo num pedido amplo. Cada bloco mostra a cobertura, e associações são correlação, nunca causa. Entende o export do HubSpot (`Cliente<>Parceiro [Demanda]`) e o formato `Empresa – Demanda`.

**Memória de reuniões (Atlas, ADR 0009):** transcrições de reunião viram embeddings num Chroma auto-hospedado, só como índice semântico — quem decide o que o vendedor pode ver continua sendo o Postgres (`Principal.owner_clause()`), checado de novo em cada trecho antes de virar resposta, nunca o Chroma sozinho.

**Propostas (Vela):** "manda uma proposta pra Acme: licença anual, 10 usuários, pro email joao@acme.com" monta um PDF no visual do Ledger — nome e valor vêm do negócio no CRM, o escopo é o que você descrever, não existe cadastro de produtos/preços — e pede confirmação antes de mandar por e-mail (uma conta Gmail única da empresa, `mailer/gmail.py`) e/ou como documento aqui mesmo no WhatsApp. Nunca escreve no HubSpot, então funciona mesmo sem `HUBSPOT_ACCESS_TOKEN`; sem e-mail configurado, degrada pra WhatsApp-only. Depois de enviado não tem Desfazer — não dá pra tirar um e-mail da caixa de entrada de alguém. `PROPOSAL_COMPANY_NAME` no `.env` define quem assina o PDF (a sua empresa, não "OmniData").

O envio por e-mail aceita duas formas de autenticação, a primeira com preferência sobre a segunda:
- **Gmail API + OAuth2** (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`): funciona mesmo quando a política do Workspace bloqueia senha de app. O client OAuth precisa ser do tipo **"Desktop app"** no Google Cloud Console (aceita o redirecionamento local de qualquer porta sem cadastro prévio); se for **"Web application"**, cadastre `http://127.0.0.1:8765` em "URIs de redirecionamento autorizados". Depois, rode uma vez: `GMAIL_CLIENT_ID=... GMAIL_CLIENT_SECRET=... uv run python scripts/gmail_oauth_setup.py` — abre uma URL de consentimento (você faz login, o script nunca vê sua senha) e imprime o `GMAIL_REFRESH_TOKEN` pra colar no `.env`.
- **SMTP + senha de app** (`GMAIL_APP_PASSWORD`, fallback se as variáveis OAuth acima estiverem vazias): Conta do Google → Segurança → Senhas de app (exige verificação em duas etapas ativada).

## Avaliação do planejador (Orion)

`uv run omnidata eval planner` mede se cada pedido vai para o especialista e a ferramenta certos, sem modelo-juiz: a resposta esperada é objetiva (agente + ferramenta), então a comparação é exata. O conjunto de frases fica em `src/omnidata/evals/planner_cases.yaml` (nomes de negócios do export real do HubSpot e alguns fictícios) e há um conjunto separado, `planner_holdout.yaml`, de frases que **nunca** foram usadas para ajustar as regras.

| Modo | Como rodar | O que mede |
|---|---|---|
| `keyword` (padrão) | `omnidata eval planner` | o roteamento sem LLM (modo degradado). Roda em qualquer lugar, sem chave |
| `llm` | `omnidata eval planner --mode llm` | o planejador de verdade (precisa de `LLM_PROVIDER` e chave no `.env`; gasta tokens) |

Cada caso termina em: **correct**, **acceptable** (cardápio no lugar de uma resposta, aceito para escritas e pedidos com vários passos, que só o LLM faz), **partial** (respondeu só parte de vários pedidos de leitura), **miss** (cardápio quando devia responder), **wrong** (respondeu outra coisa, pior que o cardápio) e **critical** (uma escrita no CRM que ninguém pediu; o comando sai com erro se houver alguma). Opções: `--json`, `--cases arquivo.yaml`, `--min-correct 0.8`.

**Modo `llm` (DeepSeek `deepseek-flash`, 20/09/2026):** primeira rodada com o prompt antigo (só nomes de ferramentas): 43% corretos no conjunto principal e 47% nas frases inéditas, sem nenhuma escrita indevida. O modelo acertava a ferramenta mas acrescentava passos de leitura desnecessários, chamava “bom dia” de fora de escopo e errava o argumento de `get_deal`. Depois de o prompt passar a trazer a descrição e os argumentos de cada ferramenta e a pedir o menor número de passos: **91% (62 de 68) no principal e 94% (16 de 17) nas inéditas, 0 escritas indevidas**. Ressalvas: são 17 frases inéditas escritas por mim (uma frase vale 6 pontos); rodada única (o modelo pode variar); e as inéditas não estão mais 100% virgens, porque a primeira rodada delas motivou a regra do “menor número de passos”. A confusão que sobra é entre “funil” e “negócios parados” (`get_pipeline_summary` × `list_deals_needing_action`).

Resultado em modo `keyword`: **85% corretos nas frases usadas para ajustar as regras** (isso só mostra que nada regrediu) e **24% nas 17 frases inéditas** (41% contando o cardápio como aceitável), sem nenhuma resposta errada nem escrita indevida. Ou seja, o modo sem LLM entende pouco fora do que foi previsto e cai no cardápio, que é o desenho; é por isso que a medida que importa é a do modo `llm`. Regra do conjunto inédito: não ajuste o roteador para fazê-lo passar; se precisar usar uma frase para corrigir algo, mova-a para o conjunto principal e escreva uma nova.

## Estrutura

```
web/                      Next.js 15 + Ledger (deploy: Vercel, Root Directory = web)
src/omnidata/
  agents/                 equipe (team.py) e validação de planos (orion.py)
  bot/                    orquestrador, ações de escrita, repositórios com Principal, gateway WhatsApp, webhook
  llm/                    chat (anthropic | openai | deepseek), transcrição, guarda de números
  rag/                    embeddings + Chroma (Atlas: memória de reuniões, ADR 0009)
  forecast/               previsão estatística determinística (Vega, ADR 0007)
  hygiene/                fila de correção de dados (Polaris)
  transcripts/            transcrições sintéticas de reunião para teste (synth.py, ingest.py)
  proposals/              PDF de proposta (Vela): template.py (Jinja2) + pdf.py (WeasyPrint)
  mailer/                 envio de e-mail (Vela): gmail.py, SMTP + app password
  telemetry.py            observabilidade (Langfuse, opcional)
  crm/hubspot/            cliente resiliente, mapeamento, escrita
  datasets/               upload: leitura CSV/XLSX, validação, importador
  integrations/airbyte/   cliente da API, aterrissagem HubSpot, mapeamento de outras fontes
  insights/               dores, termos, ERPs, demanda (determinístico; spec compartilhado com o web)
  ingest/  alerts/  api/  jobs/  security/
supabase/migrations/      SQL forward-only (bronze, silver, app, gold, serving)
docs/                     go-live.md, datasets.md, airbyte.md, templates.md, adr/ (0001–0009)
scripts/                  screenshot-hero.sh, bench_transcribe.py
```

## Começar (passo a passo)

Escolha o caminho pelo que você quer fazer. **Você não precisa de conta em HubSpot, Meta, OpenAI ou Anthropic para ver o produto funcionando.**

| Quero… | Caminho | Precisa de |
|---|---|---|
| Ver o site e o painel com dados sintéticos | [A](#a-só-o-site-e-o-painel-2-minutos) | Node 18.18+ |
| Analisar **o meu arquivo** (CSV/XLSX do CRM), sem servidor | [A](#a-só-o-site-e-o-painel-2-minutos), passo 3 | Node 18.18+ |
| Rodar o back-end, o banco e o bot (simulado) | [B](#b-back-end-com-banco-local) | Python 3.12, uv, Docker + Supabase CLI |
| Colocar no ar com HubSpot/WhatsApp reais | [docs/go-live.md](docs/go-live.md) | suas contas e chaves |

### A. Só o site e o painel (2 minutos)

```bash
git clone https://github.com/juliopessan/OmniData.git
cd OmniData/web
npm install
npm run dev          # http://localhost:3000
```

1. Abra `http://localhost:3000` e clique em **Entrar**. O login é só demonstração: qualquer e-mail válido e senha de 8+ caracteres funcionam.
2. No painel (`/dashboard`) você vê Visão geral, Negócios, Alertas, Equipe, Cockpit, Reunião de vendas, Insights e Qualidade dos dados, todos com dados sintéticos.
3. **Para usar o seu arquivo:** vá em **Datasets**, arraste o export de negócios do CRM no cartão **Negócios** (não no de Metas) e clique em **Carregar no painel**. Visão geral, Negócios, Qualidade e **Insights** passam a usar o seu arquivo. Para desfazer, use "remover".
   - **Privacidade:** nesse modo o arquivo é lido **só no seu navegador** e guardado no `localStorage` dele. Nada é enviado a servidor. Limpe o site nas configurações do navegador para apagar.
   - **Não coloque arquivos reais dentro do repositório** (principalmente em `web/public/`, que a Vercel publica). Use uma pasta `data/`, já ignorada pelo git.
   - As **Metas** e o **Cockpit** só funcionam com o servidor (caminho B) — dependem do bot rodando de verdade.
4. Modelos de planilha: no próprio cartão há o link "baixar CSV"; exemplos em `web/public/samples/` e `web/public/templates/`.

O que o arquivo de negócios precisa ter (nomes de colunas do HubSpot em pt-BR ou en, com ou sem acento):
`ID do registro`, `Nome do negócio`, `Etapa do negócio` (obrigatórias); `Valor`, `Data de fechamento`, `Proprietário do negócio`, `Associated Note` (as notas alimentam os Insights) e `Campanha…` (opcionais). Lista completa e regras em [docs/datasets.md](docs/datasets.md).

**Como ler os Insights:** cada bloco mostra a cobertura (quantos negócios têm dado para aquele bloco). Se as suas notas são de acompanhamento ("enviei proposta") e não descrevem a dor do cliente, o bloco Dores vem quase vazio; isso é limite do dado, não erro. Tipo de demanda e cliente saem do nome do negócio, nos formatos `Cliente<>Parceiro [Demanda]` ou `Empresa – Demanda`.

### B. Back-end com banco local

Pré-requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/), [Docker](https://docs.docker.com/get-docker/) e a [Supabase CLI](https://supabase.com/docs/guides/cli) (fornecem o Postgres); `ffmpeg` só se for testar áudios. Testar propostas em PDF (Vela) exige o Pango do [WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) instalado no sistema (`brew install pango` no macOS; no Homebrew do Apple Silicon, rode com `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` na frente do comando pra ele achar a lib); sem isso, `uv sync` funciona normalmente, só os testes de `proposals/` e o envio de proposta falham ao importar.

```bash
git clone https://github.com/juliopessan/OmniData.git && cd OmniData
uv sync --extra dev                # instala as dependências
cp .env.example .env               # os valores padrão já apontam para o Postgres local; nunca commite o .env
supabase start                     # Postgres local em 127.0.0.1:54322 (Docker precisa estar rodando)
uv run omnidata db migrate         # cria os schemas bronze/silver/gold/serving/app
uv run omnidata dev seed           # CRM sintético, sem dados pessoais
uv run omnidata audit              # relatório de prontidão dos dados + go/no-go
uv run omnidata serve api          # http://localhost:8000  (/healthz, /readyz, webhook); porta ocupada? use --port 8010
uv run omnidata serve worker       # noutro terminal: fila de mensagens, ingestão e alertas
make check                         # ruff + mypy + pytest
```

**Sem chaves de LLM** (`ANTHROPIC_API_KEY` ou `OPENAI_API_KEY`), o bot funciona em modo degradado por palavras-chave e menu. Com chave, o Orion planeja com o modelo. Defina `LLM_PROVIDER=anthropic|openai|deepseek` no `.env`. Não há Azure no projeto.

**Fallback de provedor (OpenRouter):** se `OPENROUTER_API_KEY` estiver definida (com `OPENROUTER_MODEL_ROUTER` e `OPENROUTER_MODEL_NARRATOR`), toda chamada ao provedor principal (`LLM_PROVIDER`) que falhar por erro do provedor (rede, limite, 5xx) tenta o OpenRouter em seguida, na mesma chamada — nunca antes de o principal falhar. Se só o OpenRouter estiver configurado, ele vira o único provedor. Se os dois faltarem, o bot cai no modo degradado, como já acontecia. A falha é registrada em log (`llm fallback: deepseek -> openrouter (...)`), e a telemetria (`app.llm_call`, e o Langfuse se estiver configurado) mostra qual provedor respondeu de fato. Um plano recusado pela validação do Orion (agente ou ferramenta errados) não aciona o fallback: isso é erro do plano, não do provedor.

**Observabilidade (opcional):** defina `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` e `LANGFUSE_BASE_URL` no `.env` (Langfuse Cloud ou auto-hospedado) para ver, por mensagem, qual especialista respondeu, o custo em tokens e a latência de cada chamada ao LLM. Sem elas, o bot funciona exatamente igual, só sem os traces.

**Testes:** os que usam banco precisam de um Postgres de teste em `TEST_DATABASE_URL` (padrão `postgresql://postgres@127.0.0.1:54399/omnidata_test`); sem ele são ignorados, e o resultado mostra quantos foram. Para rodar todos, crie esse banco e aplique as migrations nele.

**Enviar um arquivo ao banco (em vez do navegador):**

```bash
uv run omnidata dataset template --kind deals > modelo.csv                # modelo de colunas
uv run omnidata dataset import negocios.csv --kind deals                  # só valida (precisa do banco)
uv run omnidata dataset import negocios.csv --kind deals --apply          # grava; reenviar o mesmo arquivo não duplica
uv run omnidata dataset import negocios.csv --kind deals --apply --allow-partial   # grava as linhas válidas e lista as recusadas
uv run omnidata dataset import metas.csv --kind quotas --apply
uv run omnidata insights analyze negocios.csv                             # insights em JSON, sem banco
```

**Usar a tela de Datasets contra a API:** no `.env` do back-end defina `ADMIN_API_TOKEN` (qualquer segredo longo; vazio desliga o upload) e `CORS_ORIGINS=http://localhost:3000`. Em `web/.env.local` crie `NEXT_PUBLIC_API_URL=http://localhost:8000`. Reinicie os dois e preencha URL e token na página Datasets; o token fica só na memória do navegador.

**HubSpot real:** `uv run omnidata audit properties && uv run omnidata ingest backfill` (precisa de `HUBSPOT_ACCESS_TOKEN`; os nomes de propriedades vêm da auditoria, nunca de suposição). Para usar o Airbyte como camada de conectores, veja [docs/airbyte.md](docs/airbyte.md). Em produção: `docker compose up` (api + worker) num host de containers, com o Postgres gerenciado (Supabase).

### Variáveis de ambiente principais

| Variável | Para quê | Obrigatória |
|---|---|---|
| `DATABASE_URL`, `DATABASE_URL_DIRECT` | Postgres | sim (caminho B) |
| `HUBSPOT_ACCESS_TOKEN` | leitura/escrita no HubSpot | só com HubSpot real |
| `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`, `EVOLUTION_WEBHOOK_SECRET` | WhatsApp via Evolution API (ADR 0008) | só com WhatsApp real |
| `LLM_PROVIDER`, `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` | planejamento e narração; `OPENAI_API_KEY` também transcreve áudios | opcional (sem elas: modo degradado) |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL_ROUTER`, `OPENROUTER_MODEL_NARRATOR` | fallback: usado se o `LLM_PROVIDER` falhar (ou sozinho, sem um principal) | opcional |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | observabilidade (traces por mensagem) | opcional |
| `GMAIL_USER`, `GMAIL_FROM_NAME`, `PROPOSAL_COMPANY_NAME` | propostas por e-mail (Vela) | opcional (sem elas: só WhatsApp) |
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` | autenticação via Gmail API + OAuth2 (preferida) | opcional, ver `scripts/gmail_oauth_setup.py` |
| `GMAIL_APP_PASSWORD` | autenticação via SMTP (fallback, se as três acima faltarem) | opcional |
| `CHROMA_URL`, `CHROMA_COLLECTION`, `EMBEDDINGS_MODEL` | memória de reuniões (Atlas, ADR 0009) | só se usar Atlas |
| `ADMIN_API_TOKEN`, `CORS_ORIGINS` | upload de datasets pela API | só para usar a página Datasets contra a API |
| `INGEST_MODE` | `direct` (padrão) ou `airbyte` | não |
| `NEXT_PUBLIC_API_URL` (em `web/`) | liga o painel à API | não (sem ela o painel roda em modo demonstração) |

A lista completa, com comentários, está em `.env.example`.

### Deploy do site na Vercel

Importe o repositório com **Root Directory = `web`** (framework Next.js). Não exige variáveis de ambiente. `NEXT_PUBLIC_API_URL` só entra quando houver uma API hospedada: passo a passo em [docs/deploy-api.md](docs/deploy-api.md). Cada push em `main` publica sozinho.

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `Cannot find module './331.js'` ou página em branco no `npm run dev` | Cache do Next corrompido (por exemplo após rodar `next build` com o servidor aberto). `cd web && rm -rf .next && npm run dev`. |
| `cd: web: no such file or directory` | Você já está dentro de `web/`, ou fora do repositório. Use o caminho completo do clone. |
| Import pelo CLI falha com erro de conexão | O Postgres não está no ar: `supabase start` e confira `DATABASE_URL`. |
| Import recusado com `status: rejected` e "linha N · … data inválida" | O modo padrão é estrito: uma linha inválida recusa o arquivo. Corrija as linhas listadas ou use `--allow-partial` (CLI) / "importar as linhas válidas mesmo com erros" (tela). Num export real do HubSpot, poucas linhas vêm com a coluna Próxima atividade quebrada. |
| `{"detail":"Not Found"}` em `/healthz` ou `/api/datasets` | Outro programa está na porta 8000. Suba a API com `--port 8010` e ajuste `NEXT_PUBLIC_API_URL`. |
| Cartão Metas mostra "obrigatória: falta" para um export de negócios | Você soltou o arquivo no cartão errado; use o cartão **Negócios**. |
| Insights com muitos blocos vazios | Veja a cobertura no topo da página: o arquivo não traz notas, campanha ou motivo de perda. |
| "não consegue acessar a API" na página Datasets | `CORS_ORIGINS` não inclui a origem do site, ou a API não está no ar. |
| Testes de banco "skipped" | Sem Postgres de teste; veja **Testes** acima. |

## Rotas do site

| Rota | Conteúdo |
|---|---|
| `/` | Landing (Hook → Re-Hook → Meat → CTA) com números do time calculados de dados sintéticos |
| `/funcionalidades` | Blocos por tema com exemplos de conversa no WhatsApp |
| `/precos`, `/login`, `/cadastro` | Planos todos “Sob consulta”; login/cadastro **sem autenticação real** |
| `/dashboard/*` | Visão geral, negócios, alertas, **insights**, **reunião de vendas**, equipe, **datasets**, **cockpit**, qualidade dos dados |

Cada rota tem `<title>` próprio; o favicon é a mesma marca em todas (`web/src/app/**/icon.svg`). O efeito de verbos girando está em `web/src/components/SpinVerb.tsx`.

## Dados do site

`web/src/lib/seed.ts` (24 negócios sintéticos) → `web/src/lib/metrics.ts` (win rate, IC de Wilson, saúde do negócio, attention_score).
Todo número exibido é calculado ali; nada é digitado no JSX.
