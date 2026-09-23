# Hospedar a API e configurar `NEXT_PUBLIC_API_URL`

Enquanto não existir uma API no ar, o painel funciona em **modo demonstração**: o arquivo que você envia é lido só no navegador. Para validar e importar de verdade (metas, banco, bot do WhatsApp), a API precisa estar acessível por HTTPS. **Este guia não foi executado ponta a ponta**: depende de contas suas (Supabase e um host de containers). Os comandos do próprio OmniData (migrations, API, upload) foram testados num Postgres local.

## O que a variável faz (e o que não faz)

- `NEXT_PUBLIC_API_URL` só **preenche** o campo “URL da API” na página Datasets. Sem ela, o campo já aceita a URL digitada na hora, então você pode testar a API antes de configurar a Vercel.
- Ela é pública por natureza (vai no JavaScript do site). **Nunca** coloque o token de admin em variável `NEXT_PUBLIC_*`: o token é digitado na página e fica só na memória do navegador.
- A variável entra no *build*: depois de criá-la ou alterá-la, é preciso um novo deploy.

## Passo a passo

**1. Banco (Supabase).** Crie um projeto em https://supabase.com. Para dados reais de clientes use o plano Pro (o gratuito não tem backup e pausa quando ocioso). Em *Project Settings → Database* copie:
- a URL do *transaction pooler* → `DATABASE_URL`
- a URL de conexão direta → `DATABASE_URL_DIRECT`

**2. Migrations (do seu computador, uma vez).**

```bash
DATABASE_URL_DIRECT='postgresql://…direta…' DATABASE_URL='postgresql://…pooler…' uv run omnidata db migrate
```

**3. Host da API.** Qualquer host de containers serve, usando o `Dockerfile` da raiz (porta 8000, comando `omnidata serve api`). O worker (`omnidata serve worker`) é um segundo processo com a mesma imagem e as mesmas variáveis; só é necessário para o bot do WhatsApp, ingestão e alertas, não para o upload de arquivos. Exemplo com Fly.io (não testado por mim):

```bash
fly launch --no-deploy --dockerfile Dockerfile      # aceite a porta interna 8000
fly secrets set DATABASE_URL=… DATABASE_URL_DIRECT=… ADMIN_API_TOKEN=$(openssl rand -hex 32) \
  CORS_ORIGINS=https://omnidata-web-eta.vercel.app
fly deploy
```

Variáveis mínimas: `DATABASE_URL`, `DATABASE_URL_DIRECT`, `ADMIN_API_TOKEN` (segredo longo; vazio desliga o upload) e `CORS_ORIGINS` (a origem do site, sem barra final). Para o bot: `HUBSPOT_ACCESS_TOKEN`, `WHATSAPP_*`, e uma chave de LLM (veja `.env.example`).

**4. Teste a API** (troque a URL):

```bash
curl https://sua-api/healthz     # {"status":"ok"}
curl https://sua-api/readyz      # {"db":"ok",…}
curl -H "Authorization: Bearer $ADMIN_API_TOKEN" -F file=@negocios.csv https://sua-api/api/datasets/deals   # dry-run
```

Sem token, o upload responde 401.

**5. Vercel.** Em *Project → Settings → Environment Variables* crie `NEXT_PUBLIC_API_URL` = `https://sua-api` (sem barra final, ambiente *Production*) e faça um novo deploy (*Deployments → Redeploy*, ou um push). Depois, `/dashboard/datasets` deixa de mostrar “modo demonstração” e os botões “Validar no servidor” e “Importar” passam a funcionar (o token continua sendo digitado na página).

## Cuidados antes de usar dados reais

- O upload é protegido **só** pelo token de admin. Use um token longo e único, HTTPS obrigatório, e troque-o se vazar. Login real de usuários ainda não existe.
- O arquivo enviado **não é guardado**: só o hash e as contagens (`app.dataset_upload`); mas as linhas importadas entram no Postgres. Trate esse banco como dado pessoal (backup, acesso restrito, plano pago).
- **Limites antes de ler o corpo** (`src/omnidata/api/guard.py`): o token de admin e o tamanho são conferidos antes de a API ler qualquer byte do envio; uploads acima de `DATASET_MAX_BYTES` (+ 200 KB de formulário) e webhooks acima de `WEBHOOK_MAX_BYTES` (1 MB) recebem 413. Mesmo assim, ponha também um limite de corpo no proxy/balanceador na frente da API e limite de tentativas no `/api/datasets`: a API não conta tentativas de token.
- O endpoint `/webhooks/evolution` exige `EVOLUTION_WEBHOOK_SECRET`; sem ele, não o exponha. Diferente do Meta, a Evolution API não assina a chamada — o segredo é um cabeçalho (`X-OmniData-Secret`) que você mesmo define e registra no `set-webhook` (`omnidata evolution set-webhook`).
