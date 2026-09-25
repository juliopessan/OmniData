"use client";

import { TEAM } from "@/lib/team";
import { useReveal } from "@/lib/useReveal";

/** Roster do Observatório. Fonte: src/omnidata/agents/team.py -> team.json */
export function TeamGrid({ withTools = false }: { withTools?: boolean }) {
  const { ref, on } = useReveal<HTMLDivElement>();
  return (
    <div ref={ref} className="team" data-reveal={on ? "on" : "idle"}>
      {TEAM.members.map((m, i) => (
        <article key={m.key} className={m.tools.length ? "member" : "member lead"} style={{ "--i": i } as React.CSSProperties}>
          <div className="mono-tile" aria-hidden="true">{m.name.slice(0, 2)}</div>
          <div className="stack" style={{ gap: 6 }}>
            <h3 className="h3">{m.name}</h3>
            <span className="tag" style={{ alignSelf: "flex-start" }}>{m.title}</span>
            <p className="body">{m.tagline}</p>
            <p className="note">“{m.examples[0]}”</p>
            {withTools && (
              m.tools.length
                ? <div className="tools" aria-label={`Ferramentas de ${m.name}`}>{m.tools.map((t) => <code key={t}>{t}</code>)}</div>
                : <p className="note">planeja e coordena, não chama ferramentas</p>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
