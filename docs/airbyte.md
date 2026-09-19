# Airbyte como camada de conectores

Airbyte busca dados de HubSpot e de outras fontes e **aterrissa tabelas no nosso Postgres**; o OmniData mapeia essas tabelas para o `silver`.
Decisão e limites: [ADR 0006](adr/0006-airbyte-connector-layer.md). Não copiamos o monorepo do Airbyte: integramos por API e por tabelas.

```
HubSpot / Salesforce / ...  ──Airbyte (agenda própria)──►  Postgres schema `airbyte`  ──omnidata airbyte ingest──►  silver.* ──► gold/serving ──► bot
                                                                     └── outras fontes: config/integrations.yaml (mapeamento) ──► importador de datasets
```

## Montar
1. **Airbyte**: Cloud ou self-managed (siga a documentação oficial de instalação). Crie um usuário de banco só para ele, com permissão de criar o schema `airbyte`.
2. **Source HubSpot** (`airbyte/source-hubspot`; o mapeamento foi verificado contra a **6.9.2**). Habilite: `deals`, `deal_pipelines`, `owners`, `contacts`, `companies`, `deals_property_history`, `engagements_notes|tasks|calls|meetings|emails`.
3. **Destination Postgres** apontando para o nosso banco, schema `airbyte`, tabelas finais tipadas (não as `raw`). Sync incremental (append + dedup) onde o stream permitir.
4. `.env`: `INGEST_MODE=airbyte` e `AIRBYTE_SCHEMA=airbyte`. Para disparar/consultar syncs por aqui: `AIRBYTE_URL`, `AIRBYTE_CLIENT_ID`, `AIRBYTE_CLIENT_SECRET`.

```bash
uv run omnidata airbyte connections                 # lista conexões (ids para config/integrations.yaml)
uv run omnidata airbyte sync --connection-id <id>   # dispara e espera o job
uv run omnidata airbyte ingest                      # tabelas aterrissadas -> silver (incremental por _airbyte_extracted_at)
uv run omnidata airbyte ingest --full               # ignora cursores
uv run omnidata airbyte generic --name salesforce   # outra fonte via mapeamento (dry run; --apply grava)
```
Com `INGEST_MODE=airbyte` o worker roda o `ingest` a cada 15 min; quem agenda os syncs é o próprio Airbyte.

## O que foi verificado no código do conector (source-hubspot 6.9.2)
Propriedades saem achatadas como `properties_<nome>`; associações como arrays (`contacts`, `companies`, `deals`); o id do estágio é `stageId` e o do pipeline é `pipelineId`,
com `stages[].metadata.{isClosed,probability}`; `deals_property_history` traz `dealId, property, timestamp, value`. O destino Postgres preserva a caixa dos nomes (`"createdAt"`).
O mapeamento reaproveita as mesmas funções da ingestão direta, então os dois caminhos geram as mesmas linhas no silver.

## Outras fontes ("e outros")
`config/integrations.yaml` → `generic`: cada entrada mapeia colunas de uma tabela aterrissada para o dataset canônico `deals`/`quotas` e passa **pela mesma validação do upload**.
Os modelos de Salesforce e Pipedrive vêm **desativados** e com colunas **não verificadas**: inspecione a tabela real, ajuste `columns` e rode primeiro sem `--apply`.

## Limites honestos
- **Nada disto rodou contra um Airbyte real** (não havia Docker neste ambiente). Testado com tabelas no formato do Airbyte, num Postgres real, e com a API simulada. Faça um sync de teste e um `omnidata airbyte ingest` antes de confiar.
- Airbyte só lê. **Escritas no HubSpot (notas, tarefas, mudanças de etapa) continuam pelo nosso cliente**, e o Desfazer também.
- A latência passa a ser a do agendamento do Airbyte, mais lenta que o polling direto de 15 min.
- O Airbyte duplica os dados no banco: no Supabase gratuito (500 MB) estoura rápido. Use Pro ou um banco separado para o schema `airbyte`.
- O conector do HubSpot tem licença ELv2 (uso próprio; não revender como serviço gerenciado). Confira a licença de cada conector que adotar.
- O caminho por polling (`INGEST_MODE=direct`) continua o padrão e não foi removido.
