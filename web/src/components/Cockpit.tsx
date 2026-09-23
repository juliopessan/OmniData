"use client";
import { Fragment, useEffect, useState, type ReactNode } from "react";
import { Chat, type ChatMsg } from "./Chat";
import { Fig, Flag } from "./Ledger";
import { API_URL, fetchConversations, fetchMessages, type ConversationRow, type MessageRow } from "@/lib/cockpit";

const KIND_LABEL: Record<string, string> = { audio: "🎤 Áudio", buttons: "opções enviadas", list: "lista enviada" };

function preview(c: ConversationRow): string {
  if (c.last_preview) return c.last_preview;
  if (c.last_kind && c.last_kind in KIND_LABEL) return KIND_LABEL[c.last_kind];
  return c.last_received_at ? "mensagem antiga (sem texto salvo)" : "sem conversa ainda";
}

/** WhatsApp manda *negrito* como asterisco simples — o Chat, ao contrário da página estática de exemplo, mostra texto
 * real do bot, então precisa interpretar isso em vez de exibir o asterisco literal. */
function renderWaText(text: string): ReactNode {
  const parts = text.split(/(\*[^*]+\*)/g);
  return parts.map((p, i) => {
    const m = /^\*([^*]+)\*$/.exec(p);
    return m ? <b key={i}>{m[1]}</b> : <Fragment key={i}>{p}</Fragment>;
  });
}

function toMsgs(rows: MessageRow[]): ChatMsg[] {
  return rows.map((r) => ({
    me: r.direction === "in",
    text: renderWaText((r.text ?? (KIND_LABEL[r.kind] ?? `mensagem antiga, tipo ${r.kind} (sem texto salvo)`)) + (r.error ? ` — falhou: ${r.error}` : "")),
  }));
}

export function Cockpit() {
  const [api, setApi] = useState(API_URL);
  const [token, setToken] = useState("");
  const [rows, setRows] = useState<ConversationRow[] | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [thread, setThread] = useState<MessageRow[] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    if (!api || !token) return;
    setBusy(true); setError("");
    try { setRows(await fetchConversations(api, token)); }
    catch (e) { setError(e instanceof TypeError ? "Não consegui falar com a API (URL, rede ou CORS)." : (e as Error).message); setRows(null); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    if (!selected || !api || !token) { setThread(null); return; }
    let cancelled = false;
    fetchMessages(api, token, selected).then((m) => { if (!cancelled) setThread(m); }).catch(() => { if (!cancelled) setThread(null); });
    return () => { cancelled = true; };
  }, [selected, api, token]);

  const activeCount = rows?.filter((r) => r.status === "active").length ?? 0;
  const noPreviewCount = rows?.filter((r) => r.last_received_at && !r.last_preview).length ?? 0;
  const current = rows?.find((r) => r.id === selected) ?? null;

  if (!api || !token) {
    return (
      <div className="stack" style={{ gap: 16 }}>
        <div className="rule-note"><span className="rule-k">Conversas reais</span>
          <p>Informe a URL da API e o token de admin para ver as conversas de verdade dos vendedores (mesmo servidor e token do envio de Datasets).</p></div>
        <div className="grid2" style={{ gap: 16 }}>
          <div className="field"><label htmlFor="api">URL da API</label><input id="api" value={api} onChange={(e) => setApi(e.target.value)} placeholder="https://api.suaempresa.com" /></div>
          <div className="field"><label htmlFor="tok">Token de admin</label><input id="tok" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="ADMIN_API_TOKEN (só fica na memória)" /></div>
        </div>
        <div className="actions"><button className="btn" disabled={!api || !token || busy} onClick={load}>{busy ? "Carregando…" : "Entrar"}</button></div>
        {error && <Flag k="Não foi possível conectar">{error}</Flag>}
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="figs">
        <Fig value={String(rows?.length ?? 0)} label="conversas" />
        <Fig value={String(activeCount)} label="vendedores ativos" />
        {noPreviewCount > 0 && <Fig value={String(noPreviewCount)} label="sem prévia salva" />}
      </div>
      {error && <Flag k="Não foi possível concluir">{error}</Flag>}
      <div className="grid2">
        <div>
          <div className="panel-t"><h2 className="h3">Vendedores</h2><button className="linkbtn" onClick={load}>{busy ? "atualizando…" : "atualizar"}</button></div>
          <div className="tbl-wrap"><table>
            <thead><tr><th>Nome</th><th>Status</th><th>Última mensagem</th></tr></thead>
            <tbody>
              {(rows ?? []).map((r) => (
                <tr key={r.id} onClick={() => setSelected(r.id)} style={{ cursor: "pointer", background: r.id === selected ? "var(--paper-deep)" : undefined }}>
                  <td><b>{r.display_name || r.phone_e164}</b><span className="sub">{r.phone_e164}</span></td>
                  <td><span className="tag">{r.status}</span></td>
                  <td>{preview(r)}{r.last_received_at && <span className="sub mono">{new Date(r.last_received_at).toLocaleString("pt-BR")}</span>}</td>
                </tr>
              ))}
              {rows && rows.length === 0 && <tr><td colSpan={3} className="note">Nenhum vendedor convidado ou ativo ainda.</td></tr>}
            </tbody>
          </table></div>
        </div>
        {current && thread ? (
          <Chat title={current.display_name || current.phone_e164} msgs={thread.length ? toMsgs(thread) : [{ text: "Sem mensagens ainda." }]} />
        ) : (
          <div className="chat"><div className="chat-head">Conversa</div><p className="note">Selecione um vendedor à esquerda para ver a conversa.</p></div>
        )}
      </div>
    </div>
  );
}
