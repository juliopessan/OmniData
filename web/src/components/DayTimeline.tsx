"use client";

import { useReveal } from "@/lib/useReveal";

/** Os 4 horários entram em sequência ao rolar, como se o dia estivesse acontecendo — não tudo pronto de uma vez. */
export function DayTimeline({ healthCount, topName, topDays, quietName, quietDays, closed }: {
  healthCount: number; topName: string; topDays: number; quietName: string; quietDays: number; closed: number;
}) {
  const { ref, on } = useReveal<HTMLOListElement>();
  return (
    <ol ref={ref} className="day" data-reveal={on ? "on" : "idle"}>
      <li style={{ "--i": 0 } as React.CSSProperties}><time>07:30</time><div><b>Aurora</b><p>Abre o dia: os {healthCount} negócios que mais pedem a Ana, começando por <em>{topName}</em>, parado há {topDays} dias.</p></div></li>
      <li style={{ "--i": 1 } as React.CSSProperties}><time>10:12</time><div><b>Orion → Vega e Lyra</b><p>Ana pede duas coisas numa frase. Orion divide: Vega responde a meta, Lyra registra a nota. Uma resposta só.</p></div></li>
      <li style={{ "--i": 2 } as React.CSSProperties}><time>14:05</time><div><b>Altair</b><p><em>{quietName}</em> está há {quietDays} dias sem atividade e com a data de fechamento vencida. Um toque para ver, outro para adiar.</p></div></li>
      <li style={{ "--i": 3 } as React.CSSProperties}><time>17:40</time><div><b>Argus</b><p>Só {closed} negócios fechados no período. Ele avisa para não comparar vendedores ainda.</p></div></li>
    </ol>
  );
}
