# Replicando o OmniData em outro projeto

Guia para montar este produto para outro cliente ou domínio. Complementa [SPEC-BACKEND.md](SPEC-BACKEND.md)
(como o backend funciona) e [SPEC-FRONTEND.md](SPEC-FRONTEND.md) (como o painel funciona). Aqui estão o que trocar,
em que ordem montar, o que cada funcionalidade precisa cumprir e o que já deu errado em produção.

Estado de referência: `main` em `321b02d` (26/09/2026).

---

## 1. Modelo de replicação

- **Uma implantação por cliente.** O código tem `org_id` e RLS em todas as tabelas, mas nenhuma política usa isso:
  na prática é single-tenant. Cada cliente ganha seu próprio banco, sua instância do WhatsApp, seu `.env` e seu deploy.
- **Fork ou branch por projeto.** O núcleo (§2.1) deve ser igual em todos. O que muda por cliente (§2.2) fica em
  arquivos de dados e configuração, não espalhado no código. Correções do núcleo voltam para o repositório de origem.
- **Os testes são a especificação de comportamento.** O PRD original (`PRD-omnidata.md`) não está versionado. O §5
  reconstrói os critérios de aceite a partir dos testes. Se o PRD existir, ele deve entrar em `docs/` e passar a ser a
  fonte.

---

## 2. Inventário: o que muda e o que não muda

### 2.1 Núcleo: reaproveitar sem mudar

| Peça | Por que não mexer |
|---|---|
| `agents/orion.py::validate_plan`, `bot/tools/catalog.py::validate` | garantem allowlist, ≤ 3 passos, ≤ 1 escrita e escopo fora do modelo |
| `llm/guard.py::numbers_ok` + templates de fallback | garantem que nenhum número inventado chega ao usuário |
| `security/principal.py`, `security/pii_masking.py` | permissão por dono e PII fora do LLM |
| `bot/actions.py` (propor → confirmar → desfazer), `app.pending_action`, `app.audit_log` | idempotência e trilha de toda escrita |
| `bot/webhook.py`, fila `app.wa_message`, `process_next`, `requeue_stuck` | nenhuma mensagem se perde; duplicatas ignoradas |
| `api/guard.py` | auth e limite de tamanho antes de ler o corpo |
| `supabase/migrations/` | forward-only; projeto novo aplica todas |
| `forecast/`, `metrics.py` | estatística genérica |
| `llm/` (provedores, fallback, transcrição), `telemetry.py`, `rag/` | integrações genéricas, desligam sozinhas sem configuração |
| `bot/evolution.py`, `mailer/gmail.py`, `proposals/pdf.py` | adaptadores genéricos |

### 2.2 Por projeto: trocar para cada cliente

| O quê | Onde | Como foi feito aqui | O que fazer no projeto novo |
|---|---|---|---|
| Nomes de propriedades do CRM | `config/hubspot_properties.yaml` | lista esperada do PRD, não verificada | rodar `omnidata audit properties` no portal do cliente e corrigir |
| IDs de associação nota/tarefa → negócio | `crm/hubspot/writeback.py` (214, 216) | valores padrão do HubSpot | conferir criando uma nota manual |
| Dicionário de insights: dores, frases-pista, ERPs/sistemas, papéis ("ganhamos contra"), stopwords, taxonomia de motivos de perda | `insights/spec.py` | montado a partir de um export real do HubSpot pt-BR de um cliente de tax-tech | refazer com as notas do cliente novo (§4) |
| Convenção de nome do negócio: `Cliente<>Parceiro [Demanda]` e sufixo `– Novo/Renovação` | `insights/spec.py` (`COMPANY_SPLIT`, `DEMAND_BRACKET`, `DEMAND_SPLIT`), `hygiene/compute.py` e `hygiene.ts` (`name_format`) | convenção deste cliente | adaptar à convenção do cliente; se não houver, desligar `name_format` |
| Aliases de cabeçalho do upload | `datasets/spec.py` | export do HubSpot em pt-BR e en | acrescentar os nomes de coluna do export do cliente |
| Textos do bot | `bot/strings_ptbr.py` | pt-BR, tom da equipe "Observatório" | revisar tom, nomes e exemplos; manter tudo neste arquivo |
| Equipe: nomes, papéis, personas e exemplos dos agentes | `agents/team.py` | 10 agentes com nomes de estrelas | pode renomear e reescrever personas; **não** mude as allowlists sem rever `WRITE_TOOLS` e os testes |
| Regras de roteamento por palavra-chave | `bot/router.py` | vocabulário de vendas B2B em pt-BR | ajustar ao vocabulário do cliente, validando com o golden set |
| Golden set do planner | `evals/planner_cases.yaml`, `planner_holdout.yaml` | frases reais deste projeto | acrescentar frases do cliente; o holdout nunca serve para ajustar regras |
| Vocabulário da transcrição | `llm/transcribe.py::VOCAB_PROMPT` | termos de vendas em pt-BR | acrescentar produtos e jargão do cliente |
| Sinais de tom | `bot/sentiment.py` | gírias pt-BR ("valeu", "vlw") | ajustar se o público mudar |
| Proposta comercial | `proposals/templates/proposal.html`, fontes em `templates/fonts/` | layout Ledger, validade de 15 dias | trocar layout/marca se preciso; `VALIDITY_DAYS` em `proposals/template.py` |
| Transcrições sintéticas | `transcripts/synth.py` | dores, objeções e próximos passos genéricos de vendas | só para demonstração; em produção entram transcrições reais |
| Dados de exemplo | `ingest/seed.py`, `web/src/lib/seed.ts` | empresas fictícias | manter fictícios; nunca dado real de cliente |
| Site e painel | `web/src/app/page.tsx`, `funcionalidades`, `precos`, `FeatureList`, `StoryFilm` | copy do produto OmniData | reescrever copy e marca; manter o design system (§8 da SPEC do frontend) |
| JSON compartilhados com a web | `web/src/lib/*.json` | gerados | regenerar sempre que §2.2 mudar (`team`, `dataset`, `insights`, `hygiene`) |

### 2.3 Por implantação: só configuração

Tudo em variáveis de ambiente ([SPEC-BACKEND §15](SPEC-BACKEND.md)). Mínimo para um cliente funcionar:

| Obrigatório | Recomendado | Opcional |
|---|---|---|
| `DATABASE_URL`, `DATABASE_URL_DIRECT` | `ANTHROPIC_API_KEY` (ou outro `LLM_PROVIDER`) | `OPENROUTER_*` (fallback) |
| `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`, `EVOLUTION_WEBHOOK_SECRET` | `OPENAI_API_KEY` (áudio, embeddings) | `CHROMA_URL` (reuniões) |
| `APP_TIMEZONE` | `HUBSPOT_ACCESS_TOKEN` (ou upload/Airbyte) | `LANGFUSE_*` |
| | `ADMIN_API_TOKEN`, `CORS_ORIGINS` (painel) | `GMAIL_*`, `PROPOSAL_COMPANY_NAME`, `PROPOSAL_LOGO` |

---

## 3. Roteiro de montagem do zero

Cada passo termina com uma verificação. Não pule para o seguinte com a anterior falhando.

| # | Passo | Comando / ação | Verificação |
|---|---|---|---|
| 1 | Repositório | fork/branch; `uv sync --extra dev`; `cd web && npm install` | `make check` verde |
| 2 | Personalização de marca | `PROPOSAL_COMPANY_NAME`, `GMAIL_FROM_NAME`, textos em `strings_ptbr.py`, copy do site | `grep -rn "OmniData"` mostra só o que deve ficar |
| 3 | Banco | criar papel e banco dedicados (receita em [deploy-vps.md](deploy-vps.md) §2); Supabase Pro antes de dado real | `omnidata db migrate` roda as 14 migrations |
| 4 | Dados de demonstração (opcional) | `omnidata dev seed` | `omnidata audit` mostra o relatório |
| 5 | Fonte de dados real | HubSpot: private app com escopos mínimos ([go-live.md](go-live.md) §1) → `omnidata audit properties` → corrigir YAML → `omnidata ingest backfill --months 24`. Ou upload (`omnidata dataset import`) ou Airbyte ([airbyte.md](airbyte.md)) | `omnidata audit` com go/no-go por caso de uso |
| 6 | Metas | `omnidata quota import metas.csv` | "como estou na meta?" responde com atingimento |
| 7 | Dicionários do domínio | refazer §2.2 a partir dos dados do cliente (§4) e regenerar os JSON da web | testes de sincronia verdes; `omnidata insights analyze <export>` faz sentido |
| 8 | LLM e áudio | chaves do provedor; `scripts/bench_transcribe.py` com 20+ áudios reais | `omnidata eval planner --mode llm` sem regressão contra o golden set |
| 9 | API e worker | `docker compose -f docker-compose.yml -f docker-compose.traefik.yml up -d --build` com domínio e TLS | `GET /healthz` 200; `GET /readyz` com `db: ok` |
| 10 | WhatsApp | subir a Evolution; `omnidata evolution create-instance --name <nome> --webhook-url https://<api>/webhooks/evolution`; ler o QR; `EVOLUTION_INSTANCE=<nome>` | `omnidata evolution status` = `open` |
| 11 | Usuários | `omnidata user invite --phone +55... --owner <hs_owner_id> --name ... [--role manager]`; o vendedor responde **Aceito** | mensagem de boas-vindas do Orion; `app_user.status = active` |
| 12 | Opcionais | Chroma + `omnidata transcripts seed`; Langfuse; Gmail (`scripts/gmail_oauth_setup.py`); logo | cada um testado pelo roteiro do §6 |
| 13 | Painel | Vercel com Root Directory `web`; `NEXT_PUBLIC_API_URL`; origem do site em `CORS_ORIGINS` | Datasets valida um arquivo; Cockpit lista conversas |
| 14 | Backup | `omnidata db backup` e um **teste de restauração** | restauração num banco vazio funciona |
| 15 | Verificação real | roteiro do §6 no WhatsApp com um vendedor de teste | todos os itens OK; `agent_step` sem `failed` |

---

## 4. Refazendo os dicionários do domínio

Os insights só são úteis se os dicionários refletirem como o cliente escreve. Processo:

1. Exporte os negócios **com notas** do CRM do cliente (CSV). Rode `omnidata insights analyze <arquivo>` com os
   dicionários atuais e veja a cobertura de cada seção.
2. **Dores:** procure nas notas os rótulos que o time usa ("Dor validada:", "Problema:", "Desafio:") e ajuste
   `PAIN_LABELS`; acrescente frases-pista frequentes em `PAIN_CUES`.
3. **Sistemas:** liste os ERPs, CRMs e concorrentes citados e acrescente em `SYSTEMS` com aliases e categoria.
4. **Motivos de perda:** agrupe os motivos reais em `LOSS_TAXONOMY` (código, rótulo e palavras-chave).
5. **Nome do negócio:** se o cliente tem convenção (empresa, parceiro, demanda), ajuste `COMPANY_SPLIT`,
   `DEMAND_BRACKET` e `DEMAND_SPLIT` e a regra `name_format` da higiene. Isso também muda o nome do cliente na proposta.
6. **Stopwords:** acrescente o jargão que aparece em todas as notas e não diz nada.
7. Regenere `insights-spec.json` e `hygiene-spec.json`, rode os testes de insights e compare a cobertura antes e depois.

Nada disso usa LLM: são contagens sobre dicionários revisáveis. Não troque por classificação via modelo sem ADR.

---

## 5. Catálogo de funcionalidades e critérios de aceite

Reconstruído dos testes. Cada linha é um critério que **tem teste**; o teste citado é a referência. Um projeto
replicado deve manter todos verdes.

### 5.1 Acesso e consentimento

| Critério | Teste |
|---|---|
| Número desconhecido recebe recusa fixa e nenhum dado | `test_unknown_number_gets_refusal_and_no_data` (FR-BOT-1) |
| Convidado vira ativo só ao responder "Aceito", com versão do texto e data do consentimento | `test_onboarding_aceito_activates_and_records_consent` |
| Pausado e revogado não recebem nada | `test_revoked_and_paused_users_get_nothing` |
| Apagar usuário remove tudo ligado a ele (LGPD) | `test_user_invite_and_erase_lgpd` |
| Vendedor não vê nem escreve em negócio de outro vendedor | `test_permission_matrix_rep_cannot_see_other_reps_deals`, `test_rep_cannot_write_to_another_reps_deal` |
| O modelo nunca define o escopo de dono | `test_model_can_never_supply_owner_scope`, `test_owner_scope_never_comes_from_the_plan` |
| Rate limit por número | `test_rate_limit` |

### 5.2 Conversa e roteamento

| Critério | Teste |
|---|---|
| Pedido com duas partes é dividido entre dois agentes e cada trecho vem assinado | `test_orion_splits_request_between_vega_and_lyra_and_signs_both` |
| Plano inválido nunca executa; duas escritas no mesmo plano são rejeitadas | `test_invalid_plan_is_never_executed_and_falls_back`, `test_two_writes_in_one_plan_are_rejected` |
| Endereçar um agente ("Vega, ...") restringe o plano a ele; agente errado aponta o dono | `test_direct_address_routes_to_that_agent_only`, `test_addressing_the_wrong_agent_points_to_the_owner` |
| Seguimento ("isso", "essas causas") usa só a última troca | `test_orion_sees_the_previous_exchange_to_resolve_a_follow_up` |
| Sem LLM: palavras-chave e depois menu; nunca escreve | `test_llm_down_falls_back_to_keywords_then_menu`, `test_keyword_mode_never_writes_and_never_gives_a_new_wrong_answer` |
| "Fora do escopo" do LLM só vale se as palavras-chave também não acharem nada | `test_llm_false_negative_oos_gets_a_second_opinion_from_keywords` |
| Resposta numerada ("1", "5") escolhe a opção da última mensagem, não replaneja | `test_numbered_reply_confirms_instead_of_replanning`, `test_numbered_reply_picks_the_menu_option`, `test_a_bare_number_without_options_before_it_is_not_an_option` |
| "Lista os especialistas" responde com a equipe | `test_list_the_specialists_is_the_team_answer_not_out_of_scope` |
| Negócio ambíguo gera lista; a escolha completa a ação pedida | `test_ambiguous_deal_gets_list_and_pick_completes_the_action` |
| "Valeu" solto recebe reação 👍, não menu | `test_bare_thanks_gets_a_reaction_not_a_reply` |
| Texto ao planner é mascarado (PII) | `test_router_input_is_pii_masked` |

### 5.3 Números e narração

| Critério | Teste |
|---|---|
| Narração com número inventado é descartada e o template entra | `test_number_guard_falls_back_when_narrator_invents_a_number`, `test_number_guard_catches_invented_numbers` |
| Arredondamentos e percentuais fiéis passam | `test_number_guard_accepts_faithful_and_rounded_numbers` |
| Sem dados, a resposta diz isso; nunca devolve zeros inventados | `test_empty_data_gives_an_honest_answer_not_zeroes`, `test_no_data_never_invents_anything` |
| Frustração muda o tom, nunca os números | `test_negative_sentiment_shapes_the_narrator_tone_not_the_numbers` |
| Previsão não mostra probabilidade abaixo do mínimo de fechados | `test_no_forecast_below_the_minimum_of_closed_deals_and_no_percentage_is_invented`, `test_vega_answers_the_forecast_signed_and_never_invents_a_probability` |

### 5.4 Escritas

| Critério | Teste |
|---|---|
| Nota: recibo com Editar/Desfazer; desfazer em até 24h | `test_note_receipt_and_undo` |
| Alteração de negócio pede confirmação; confirmar duas vezes executa uma vez | `test_deal_update_requires_confirmation_and_double_confirm_executes_once` |
| "pode"/"cancela" valem como os botões | `test_free_text_pode_equals_confirm_and_cancela_equals_cancel` |
| Confirmação expirada é recusada; desfazer após 24h é recusado | `test_expired_confirmation_is_rejected`, `test_undo_after_24h_is_refused` |
| Desfazer não sobrescreve alteração de colega | `test_stale_undo_refuses_when_colleague_changed_value` |
| Falha do CRM marca a ação como falha, nunca sucesso silencioso | `test_hubspot_5xx_marks_failed_never_silent_success` |
| Escrita pedida por áudio continua exigindo confirmação | `test_audio_write_still_needs_confirmation_after_transcription` |
| Meta pessoal: definir e acompanhar progresso real | `test_set_goal_then_get_goal_status_shows_real_progress` |

### 5.5 Propostas (Vela)

| Critério | Teste |
|---|---|
| Só WhatsApp: basta o negócio (sem escopo, sem e-mail), gera e manda na hora para o próprio vendedor | `test_send_proposal_whatsapp_only_from_a_pasted_list_line_without_scope`, `test_send_proposal_needs_only_the_deal` |
| Com e-mail: confirmação antes; envia e-mail com PDF e documento no WhatsApp | `test_send_proposal_requires_confirmation_then_emails_and_sends_whatsapp_document` |
| E-mail é obrigatório quando o canal inclui e-mail | `test_send_proposal_email_channel_requires_recipient_email` |
| Sem e-mail configurado: avisa e marca como falha | `test_send_proposal_without_emailer_reports_email_down_and_marks_failed` |
| PDF nunca mostra o rótulo cru do CRM; sem escopo não inventa itens | `test_client_name_never_carries_the_crm_tag`, `test_render_html_without_scope_states_crm_only_and_invents_no_items` |
| Pedido sem negócio pede o negócio, sem pedir e-mail | `test_needs_info_for_vela_never_asks_for_an_email` |

### 5.6 Áudio, alertas e rotina

| Critério | Teste |
|---|---|
| Áudio é transcrito, ecoado ("🎤 Entendi"), roteado e custeado | `test_audio_is_transcribed_echoed_routed_and_costed` |
| Áudio longo/grande/ilegível é recusado antes de chamar a API | `test_too_long_is_refused_before_any_api_call`, `test_too_big_and_undecodable_are_refused_without_api_call` |
| Alertas respeitam limite diário, horário de silêncio e soneca | `test_alert_engine_budget_quiet_hours_snooze_and_telemetry` |
| Resumo matinal uma vez por dia útil | `test_morning_brief_template_once_per_day_business_days_only` |
| Recap das 18h relata só o que aconteceu, uma vez por dia | `test_evening_recap_reports_real_progress_and_respects_the_daily_gate` |

### 5.7 Dados de entrada

| Critério | Teste |
|---|---|
| Backfill idempotente e retomável; incremental pega edições em um ciclo | `test_backfill_row_parity_and_idempotent`, `test_backfill_resumes_without_refetching_completed_windows`, `test_incremental_picks_up_edits_within_one_cycle` |
| Ganho/perdido vêm dos metadados da etapa, não do nome | `test_won_lost_come_from_stage_metadata_not_names` |
| E-mail de contato nunca é guardado em claro | `test_contact_email_is_hashed_never_stored` |
| Upload: dry run por padrão; erros por linha; reimportar não duplica | `test_default_is_dry_run_then_apply`, `test_row_errors_carry_line_and_header`, `test_reimport_is_idempotent_and_replace_swaps_the_set` |
| Export real do HubSpot pt-BR é lido inteiro | `test_real_export_maps_every_column_and_is_valid` |
| Contrato das views `serving.*` | `test_serving_views_have_expected_contract` |

### 5.8 API e segurança

| Critério | Teste |
|---|---|
| Token errado é recusado sem ler o corpo; corpo grande é cortado | `test_a_bad_or_missing_token_is_refused_without_reading_any_of_the_body`, `test_a_declared_size_over_the_limit_is_refused_before_reading` |
| Webhook: segredo, deduplicação, ignora as próprias mensagens | `test_webhook_secret_dedupe_ignores_own_messages_and_persists` |
| Erros nunca vazam chaves | `test_errors_never_leak_credentials`, `test_evolution_error_raises_without_leaking_the_api_key` |
| Migrations forward-only | `test_migrations_are_forward_only_and_rls_has_no_policies` |

---

## 6. Verificação manual no WhatsApp

Com um vendedor de teste ativo, rodar e marcar. Trocar os nomes pelos negócios reais do banco.

1. `oi` → saudação, sem erro. `quem está na equipe?` e `lista os especialistas` → a equipe.
2. `como estou na meta?` em **texto** e depois em **áudio** → mesmos números; o áudio começa com "🎤 Entendi".
3. `vou bater a meta?` → previsão com faixa, ou aviso de amostra pequena.
4. `quais negócios preciso mexer?` e `detalhes do negócio <nome>`.
5. `nota na <negócio>: CFO aprovou o escopo` → recibo com Editar/Desfazer; depois `desfazer` → "Desfeito".
6. Mudar a etapa de um negócio → Confirmar/Ajustar/Cancelar; responder **`1`** → executa uma vez; repetir e
   responder **`pode`**; repetir e responder **`cancela`**.
7. `quero fechar 3 negócios até sexta` → meta definida; `como estou na minha meta?`.
8. `como estão meus dados?`, `o que preciso corrigir nos meus negócios?`.
9. `preciso de um script para uma reunião difícil` → objeções reais; `o que ficou combinado com <empresa>?` → trecho
   de reunião (se Chroma estiver ligado).
10. `Vela, manda a proposta da <negócio> aqui no WhatsApp` → PDF direto, sem confirmação.
11. `manda uma proposta pra <negócio>: <escopo>, pro email <seu e-mail>` → confirmação; `1` → e-mail com PDF.
12. Colar uma linha da lista do bot com valor (`Empresa X – Novo (R$ 120.000)`) → acha o negócio certo.
13. Nome ambíguo → lista para escolher; responder com o número.
14. `valeu` → reação 👍.
15. Pergunta fora de vendas → resposta educada de fora do escopo.
16. Mensagem num **grupo** onde o número do bot está → nenhuma resposta.

Depois: `app.agent_step` sem `failed`, `app.audit_log` com as escritas, nenhum `skip job` persistente nos logs do worker.

---

## 7. Lições aprendidas (sintoma → causa → prevenção)

### WhatsApp / Evolution

| Sintoma | Causa | Prevenção |
|---|---|---|
| O bot respondia em todo grupo do número conectado | o webhook não filtrava `@g.us` | filtro em `webhook.persist_inbound`; item 16 do §6 |
| Responder "1" gerava outra proposta; "5" no menu devolvia o menu | a Evolution mostra botões como texto numerado e nada traduzia o número de volta | `send` grava `options`; `_numbered_option` mapeia antes do LLM |
| `set_webhook` com 400 | a Evolution exige o corpo dentro de `{"webhook": {...}}`, ao contrário de parte da documentação | usar `EvolutionAdminClient.set_webhook` |
| `sendPresence` com 400 | campo `delay` obrigatório e não documentado | já tratado; presença nunca bloqueia a resposta |
| Jobs com `skip job 7006: ... Connection Closed`; documento não enviado | instância do WhatsApp desconectada | `omnidata evolution status`; reconectar pelo QR; o worker se recupera sozinho |
| Botões/listas nativos não aparecem | UI interativa do Baileys não é confiável em aparelhos reais | tudo sai como texto numerado |

### Roteamento e LLM

| Sintoma | Causa | Prevenção |
|---|---|---|
| Bot repete "Claro! Só me falta..." sem erro nenhum no log | o planner respondeu `PRECISA_MAIS` porque a ferramenta exigia um argumento que o usuário não tem | argumento opcional quando o dado pode vir do CRM; dica específica por agente (`NEEDS_INFO_DETAIL`); diagnosticar rodando o planner real no container |
| Pedido válido cai no menu | argumento obrigatório condicional (ex. e-mail só quando o canal inclui e-mail) sem default: o pydantic rejeita e `catalog.validate` devolve `None` em silêncio | default + `model_validator`; teste com o caso real |
| `set_goal` rejeitado duas vezes em produção | o planner não sabia os valores literais do enum | `orion._tool_line` lista os valores aceitos de todo enum |
| Negócio não encontrado ao colar a linha da lista | "(R$ 120.000)" virava tokens que nunca batiam; "890" achava "1890" | `deal_query_tokens`, número como palavra inteira, nome exato vence |
| Número estranho numa resposta | narrador inventou | trava de números + template; `audit_log.number_guard_fallback` mede a frequência |

### PDF (WeasyPrint 62.x)

| Sintoma | Causa | Prevenção |
|---|---|---|
| `AttributeError ... transform` ao gerar PDF | `pydyf` 0.11+ quebra o WeasyPrint 62 | `pydyf<0.11` no `pyproject.toml` |
| Colunas sobrepostas | suporte parcial a flexbox/`gap` | layout em tabelas |
| Seções fora de ordem | `<section>` sem `display: block` | `div` + `display: block` explícito |
| Página meio em branco | `break-inside: avoid` num bloco que não coube | ritmo vertical mais justo |
| Fonte genérica no container | imagem Debian sem as fontes da marca | fontes OFL embutidas + `base_url` no `HTML()` |
| `cannot load library 'gobject-2.0-0'` no macOS | Pango do Homebrew fora do caminho | `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` |

### Gmail

| Sintoma | Causa | Prevenção |
|---|---|---|
| `redirect_uri_mismatch` | cliente OAuth do tipo "Web application" exige URI cadastrada | usar "Desktop app", ou cadastrar `http://127.0.0.1:8765` (porta fixa do script) |
| URL de consentimento não aparece | saída do Python com buffer em segundo plano | `python -u` |
| Senha de app bloqueada | política do Workspace | preferir Gmail API + OAuth2 |

### Banco, deploy e ferramentas

| Sintoma | Causa | Prevenção |
|---|---|---|
| Senha do papel do banco não definida, sem erro | heredoc em `docker exec` sem `-i` não recebe nada | sempre `docker exec -i`; e `:'var'` do psql não expande dentro de `DO $$` |
| `git pull` falha na VPS | o compose fica numa pasta e o checkout do código em `app/` dentro dela | documentar o caminho do checkout por implantação |
| `pytest`/`mypy` somem do venv | `uv sync` sem `--extra dev` | sempre `uv sync --extra dev` |
| `omnidata` não importa localmente | pacote não instalado no venv | `PYTHONPATH=src uv run python -m omnidata.cli ...` |
| `team.json` zerado | `omnidata ... > arquivo` falhou e o redirecionamento truncou o arquivo | exportar para um temporário e mover |
| Diff enorme sem mudança real | `ruff format` reformata o estilo denso do projeto | `make check` usa só `ruff check`; não rodar `ruff format` no projeto todo |

### Segredos

- Chave colada em chat é chave vazada: rotacionar.
- Nunca passar segredo como argumento literal de comando; escrever num arquivo temporário, aplicar e apagar.
- Logs só com tipo de exceção e contagens; nunca corpo de mensagem, telefone ou chave.

---

## 8. Checklist de go-live por cliente

- [ ] `make check` verde; `omnidata eval planner` sem regressão.
- [ ] `omnidata audit properties` sem propriedade faltando; associações 214/216 conferidas.
- [ ] `omnidata audit` com go/no-go revisado com o cliente (o que o painel e o bot podem afirmar).
- [ ] Dicionários do domínio refeitos (§4) e JSON da web regenerados.
- [ ] Supabase Pro (ou banco com backup) e teste de restauração feito.
- [ ] Base legal LGPD, texto de consentimento (`CONSENT_VERSION`) e retenção aprovados.
- [ ] Metas importadas.
- [ ] 20+ áudios reais no `bench_transcribe.py`.
- [ ] Roteiro do §6 completo com um vendedor de teste.
- [ ] `ADMIN_API_TOKEN` longo e aleatório; rate limit no proxy enquanto o login do painel não for real.
- [ ] Monitorar na primeira semana: `agent_step` com `failed`/`rejected`, `number_guard_fallback`, custo em
      `v_cost_per_user`, `skip job` no worker.

---

## 9. O que ainda falta para replicar com segurança

- **PRD versionado.** Os critérios do §5 vêm dos testes; faltam os requisitos originais (personas, escopo, métricas
  de sucesso). Colocar `PRD-omnidata.md` em `docs/`.
- **Multi-tenant de verdade**, se a ideia for um só deploy para vários clientes: políticas de RLS por `org_id` e
  `org_id` resolvido a partir do usuário.
- **Login real no painel** e API de leitura sobre `serving.*` ([SPEC-FRONTEND §13](SPEC-FRONTEND.md)).
- **Parametrizar o domínio sem editar código:** hoje `insights/spec.py` e as regras de nome são código Python. Mover
  para arquivos de configuração por cliente reduziria o fork a configuração pura.
- **Testes de paridade** dos portes TS de insights, higiene e datasets, e de sincronia do `hygiene-spec.json`.
