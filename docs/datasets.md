# Upload de datasets

Suba uma exportação do CRM (`deals`) ou as metas (`quotas`) por **CSV ou XLSX**: pela página `/dashboard/datasets`, pela API ou pela CLI.
Fluxo: **ler → validar linha a linha → (só então) importar**, tudo idempotente e em uma única transação.

```bash
uv run omnidata dataset import negocios.csv --kind deals            # só valida
uv run omnidata dataset import negocios.csv --kind deals --apply    # grava
uv run omnidata dataset import metas.csv --kind quotas --apply
uv run omnidata dataset template --kind deals > modelo.csv
```

```bash
curl -H "Authorization: Bearer $ADMIN_API_TOKEN" -F file=@negocios.csv https://sua-api/api/datasets/deals                 # dry run (padrão)
curl -H "Authorization: Bearer $ADMIN_API_TOKEN" -F file=@negocios.csv -F dry_run=false https://sua-api/api/datasets/deals   # grava
```

## Formato `deals` (baseado numa exportação real do HubSpot em pt-BR)
Cabeçalhos são reconhecidos sem distinguir acento, caixa ou pontuação, em português ou inglês (lista completa: `omnidata dataset spec`).

| Coluna | Obrigatória | Observação |
|---|---|---|
| `ID do registro` | sim | único por linha |
| `Nome do negócio` | sim | |
| `Etapa do negócio` | sim | **ganho/perdido saem do nome da etapa** (“Fechado ganho”, “Closed Won”, …). Ou use a coluna `Status` |
| `Valor`, `Data de fechamento` | não | aceita `1.234,56`, `R$ 1.234,56`, `1,234.56`; datas `AAAA-MM-DD` ou `DD/MM/AAAA` (horário de São Paulo) |
| `Proprietário do negócio` | não | nome ou id. Nomes que já existem no HubSpot são reaproveitados; os novos viram `up:<nome>` |
| `Próxima atividade` | não | vira uma tarefa aberta, para “sem próximo passo” ser calculado dos dados |
| `Motivo da perda` | não | se faltar, extrai de “Motivo da perda: …” nas notas (só para perdidos) |
| `Associated Note` / `Associated Note IDs` | não | notas separadas por ` \| `; `--no-notes` para não importar o texto |
| `Data de criação` | não | **sem ela não dá para calcular “parado na etapa” nem ciclo**: a exportação padrão do HubSpot não traz |
| `Pontuação do negócio` | não | reconhecida mas **não importada** (é previsão do CRM, não fato) |

Colunas desconhecidas (telefone, e-mail, CPF…) **nunca são lidas nem importadas**; aparecem no relatório como ignoradas.

## Regras
- Etapas abertas ganham ordem pelo nome (qualificação → reunião → apresentação → proposta → negociação → contrato) ou pela sua `--stage-order`; a probabilidade sobe de 10% a 90% ao longo do funil. O relatório mostra a ordem usada.
- Erro em qualquer linha **bloqueia** a importação, a menos que você marque “importar as linhas válidas” (`--allow-partial`). O relatório traz linha, coluna e mensagem.
- Reenviar o mesmo arquivo não duplica. `--replace` apaga antes tudo o que veio de upload (ids `up:`).
- Ids importados têm prefixo (`up:` ou o nome da fonte Airbyte), então nunca colidem com os do HubSpot. **Se você importa do HubSpot direto e também sobe o CSV do mesmo CRM, os negócios aparecem duas vezes**: use um caminho só por vez.
- Limites: 10 MB e 100 mil linhas por arquivo (`DATASET_MAX_BYTES`, `DATASET_MAX_ROWS`), 60 colunas. O arquivo **não é guardado**: só o hash SHA-256 e as contagens (`app.dataset_upload`).

## Segurança
`/api/datasets*` exige `Authorization: Bearer $ADMIN_API_TOKEN` (comparação em tempo constante); sem o token configurado, responde 503. Para a página chamar a API do navegador, defina `CORS_ORIGINS` com a origem do site e `NEXT_PUBLIC_API_URL` no build do front. O login do site ainda é demonstração: **o token é o que protege o upload**. Falta limitar a taxa de requisições.
