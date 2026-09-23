import { API_URL } from "./api";

export { API_URL };

export interface ConversationRow {
  id: string; display_name: string | null; phone_e164: string; hs_owner_id: string; status: string;
  last_direction: "in" | "out" | null; last_kind: string | null; last_preview: string | null; last_received_at: string | null;
}

export interface MessageRow {
  direction: "in" | "out"; kind: string; text: string | null; status: string; error: string | null; received_at: string;
}

async function get<T>(api: string, token: string, path: string): Promise<T> {
  const r = await fetch(`${api.replace(/\/$/, "")}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (r.status === 401) throw new Error("Token inválido.");
  if (r.status === 503) throw new Error("Cockpit desativado no servidor (ADMIN_API_TOKEN não configurado).");
  if (!r.ok) throw new Error(`Erro ${r.status} no servidor.`);
  return r.json() as Promise<T>;
}

export const fetchConversations = (api: string, token: string) => get<ConversationRow[]>(api, token, "/api/cockpit/conversations");
export const fetchMessages = (api: string, token: string, userId: string) =>
  get<MessageRow[]>(api, token, `/api/cockpit/conversations/${userId}/messages`);
