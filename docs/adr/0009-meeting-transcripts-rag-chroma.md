# ADR 0009: Meeting transcripts + semantic search (Atlas), Chroma as index only, Postgres as the permission boundary
- Status: accepted · Date: 2026-09-23

## Context
Depois da Nova (Coach de Vendas, script/objection help sourced from `insight_analysis`), o pedido seguinte foi um agente que
guarda o que foi dito em reuniões e responde perguntas por assunto ("o que ficou combinado com a Acme?"). Isso é busca
semântica — nada no projeto até aqui precisava disso; tudo é SQL determinístico sobre `serving.*`. É a primeira dependência
externa nova desde a Evolution API (ADR 0008), então vira decisão de arquitetura, não só mais uma ferramenta.

O Chroma já roda na VPS de produção (`chroma-1vzj-chromadb-1`), compartilhado com outras ferramentas do mesmo jeito que o
Postgres e o Evolution API já estavam lá antes do OmniData chegar (ver `docs/deploy-vps.md`). Não precisamos subir nada novo,
só conectar.

## Decision
- **Chroma é um índice, nunca a fonte de permissão.** `app.meeting_transcript` (Postgres, migração 0012) é a fonte de verdade;
  o Chroma guarda só o embedding e `{transcript_id, hs_owner_id}` como metadado — um pré-filtro grosseiro. Toda consulta
  (`bot/repo.py::meeting_transcripts_by_ids`) refiltra os candidatos do Chroma pelo Postgres via `Principal.owner_clause()`
  (CLAUDE.md regra 7) antes de qualquer trecho virar resposta; um id que não passe nesse filtro é descartado ali, nunca
  mostrado. Isso vale mesmo que o filtro de metadado do Chroma falhe ou fique desatualizado — não é a última linha de defesa,
  é só uma otimização.
- **Embeddings via OpenAI** (`text-embedding-3-small`, `rag/embeddings.py`), reaproveitando `OPENAI_API_KEY` (já configurada em
  produção para transcrição de áudio, ADR 0004). Sem chave nova.
- **Clientes síncronos** (`rag/embeddings.py`, `rag/chroma.py`), no mesmo espírito de `bot/repo.py` (psycopg também é síncrono).
  O worker processa uma mensagem por vez (`jobs/worker.py::run`), então não há concorrência real a perder bloqueando por uma
  chamada HTTP — mesma lógica já aceita pra toda leitura SQL existente.
- **Transcrições sintéticas para teste** (`transcripts/synth.py`): templates determinísticos em Python (não geradas por LLM,
  por custo e previsibilidade), amarradas a negócios que já existem no banco de destino (`silver.deal`, nome/valor/dono reais)
  — nunca uma empresa inventada solta. CLI: `omnidata transcripts seed --owner <id> --n <N>`.
- Agente: **Atlas**, "Memória de Reuniões", ferramenta `search_meeting_notes` (busca por assunto, não por nome exato do
  negócio). Como todo especialista, só essa ferramenta em sua allowlist (`agents/team.py`).

## Consequences
Mais uma dependência externa em produção (Chroma), mas já compartilhada e operada fora do OmniData — mesmo risco operacional
que Evolution API e o Postgres compartilhado já carregam. Custo de embeddings é baixo (`text-embedding-3-small`). Sem
transcrição real de reunião ainda conectada (nenhuma integração com Zoom/Meet/Gong): por ora só o que for inserido via
`omnidata transcripts seed` (sintético) ou manualmente. Não existe `PRD-omnidata.md` versionado neste repo — as ADRs
anteriores já citam um "PRD §5" que não está aqui; sigo o padrão existente e não invento o arquivo.

### A verificar antes de dado real
`chromadb.HttpClient` foi usado sem testar contra a instância real da VPS neste PR (só testado com um fake em memória nos
testes automatizados) — antes de indexar uma transcrição real, rodar `omnidata transcripts seed` contra a VPS e conferir que
o `upsert`/`query` funcionam com a versão do servidor (`chromadb/chroma:1.0.15`), a mesma disciplina que a ADR 0008 aplicou à
Evolution API e a ADR 0006 ao Airbyte.
