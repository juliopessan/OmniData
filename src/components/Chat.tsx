import type { ReactNode } from "react";
export type ChatMsg = { me?: boolean; text: ReactNode; buttons?: string[] };
export function Chat({ title, msgs }: { title: string; msgs: ChatMsg[] }) {
  return (
    <div className="chat" aria-label={`Exemplo de conversa: ${title}`}>
      <div className="chat-head">WhatsApp · {title}</div>
      {msgs.map((m, i) => (
        <div key={i} className={`msg${m.me ? " me" : ""}`}>
          {m.text}
          {m.buttons && <div className="btns">{m.buttons.map((b) => <span key={b}>{b}</span>)}</div>}
        </div>
      ))}
    </div>
  );
}
